"""S&P 500 数据组合入口：同一份成员快照驱动行情与基本面获取。

调用方先用 prepare_members 准备 universe，再创建 SP500Data。构造时只复制并校验
配置；实际下载/解析发生在 prices/fundamentals 方法中，写库由 write 开关控制。
返回值始终是 DataFrame，字段及证券筛选放到 readers 的数据库查询接口中。

基本面从本地 SEC ZIP 读取，保留原始申报、比较期和重述版本，不提前取最新值。
成员快照单独保存；更新成员不会连带删除退出证券的行情或财务历史。
"""

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .sources.sec.bulk import parse_company_facts
from .sources.sec.fields import FIELDS, get_field_concepts
from .sources.sec.normalize import (
    FUNDAMENTAL_COLUMNS,
    derive_quarters,
    standardize_facts,
)
from .sources.yahoo import get_prices
from .universe import PREDECESSOR_CIKS, format_cik, normalize_members
from .writer import save_fundamentals, save_members, save_prices

# 标准表的版本主键与数据库一致；同一期间的不同申报文件仍分别保留。
KEY = ["ticker", "field", "period_end", "period_months", "accn"]


class SP500Data:
    """持有固定 universe、数据源位置及默认写入设置的组合接口。

    Attributes:
        report: 最近一次获取的统计, 新调用会整体覆盖旧报告, 调用前是空 dict。
            kind 标明来源("prices"/"fundamentals"), written 仅在写入成功后为
            True, rows 是返回行数; 其余键随来源不同(行情有 missing_tickers,
            基本面有 missing_mappings/missing_files/missing_fields 等)。
            members() 不改动该报告。
        quarantine: 最近一次基本面处理中隔离的标准事实，与基本面使用相同列结构。
            日期倒置、截止日晚于申报日或非有限值不能参与单季推导。
    """

    def __init__(
        self,
        *,
        universe: pd.DataFrame,
        companyfacts: str | Path | None = None,
        db: str | Path | None = None,
        write: bool = False,
    ):
        """配置对象，不发起网络请求，也不检查数据库或 ZIP 是否已经存在。

        Args:
            universe: 至少包含 ticker/name 的成员 DataFrame。ticker 统一为大写及
                短横线写法；cik 列可省略，行情仍可获取，基本面读取时报告缺映射。
            companyfacts: 本地 companyfacts ZIP 路径；仅使用行情时可以省略。
            db: DuckDB 文件路径。读取结果不入库时可以省略。
            write: 方法的默认入库开关；每个方法的 write 参数可单次覆盖。

        Raises:
            ValueError: 成员为空、ticker 重复、必需列缺失、标识无效，或开启写入但
                没有提供数据库路径。
        """
        # 拷贝快照，避免外部 DataFrame 的后续修改改变两个数据源的证券范围。
        self._universe = normalize_members(universe)
        self.companyfacts = Path(companyfacts) if companyfacts is not None else None
        self.db = Path(db) if db is not None else None
        self.write = write
        if write and self.db is None:
            raise ValueError("write=True 需要 db")
        self.report = {}
        self.quarantine = pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)

    def members(self, *, write: bool | None = None) -> pd.DataFrame:
        """返回构造时固定的成员快照，并按开关保存当前成员表。

        Args:
            write: None 继承对象默认值，True/False 显式覆盖。

        Returns:
            成员 DataFrame 的副本；调用方修改它不会影响本对象。

        Notes:
            写入替换整个 constituents 快照，并规范为 schema 定义的成员列。
            不维护历史成员资格区间，也不删除行情或基本面历史。
        """
        should_write = self.write if write is None else write
        if should_write:
            if self.db is None:
                raise ValueError("write=True 需要 db")
            save_members(self.db, self._universe)
        return self._universe.copy(deep=True)

    def fundamentals(
        self, *, write: bool | None = None, allow_partial: bool = False
    ) -> pd.DataFrame:
        """解析整个 universe 的全部标准基本面字段及历史申报版本。

        Args:
            write: None 继承对象默认设置；False 只解析，完全不连接数据库。
            allow_partial: 默认 False，缺 CIK 映射或任一主体文件即报错且不写库。
                True 时跳过来源不完整的整个 ticker，保留该 ticker 的旧库数据。

        Returns:
            列为 FUNDAMENTAL_COLUMNS 的标准长表，按版本主键排序。period_months=0
            表示时点值，3/6/9/12 表示期间长度；derived 标识累计差推导的单季值。
            filed/accn 保留申报版本，后续由数据库读取接口做 PIT 筛选。

        Raises:
            ValueError: 缺少 ZIP 配置、来源不完整或文件内 CIK 与文件名不一致。
            OSError / zipfile.BadZipFile: 本地 ZIP 不可读取或损坏。
            duckdb.Error: 写入失败；写入事务回滚，错误继续向调用方传播。

        Notes:
            全量指 FIELDS 定义的标准字段，不是 SEC 全部 XBRL 科目。
            来源完整但未命中某个科目属于字段缺失，记录在 report['missing_fields']。
            写入只替换成功 ticker 的全部标准字段；不会清空其他证券或未管理字段。
        """
        should_write = self.write if write is None else write
        if should_write and self.db is None:
            raise ValueError("write=True 需要 db")
        selected_fields = list(FIELDS)
        symbols = self._universe.ticker.tolist()
        self.report = {
            "kind": "fundamentals",
            "missing_mappings": [],
            "missing_files": [],
            "written": False,
        }
        self.quarantine = pd.DataFrame(columns=FUNDAMENTAL_COLUMNS)
        frames, rejected, completed = [], [], []
        members = self._universe.set_index("ticker")
        if self.companyfacts is None:
            raise ValueError("fundamentals() 需要 companyfacts ZIP 路径")
        with zipfile.ZipFile(self.companyfacts) as archive:
            names = set(archive.namelist())
            for ticker in symbols:
                cik = members.loc[ticker, "cik"]
                if cik is None:
                    self.report["missing_mappings"].append(ticker)
                    continue
                # 控股重组后的 ticker 可能同时需要前身和当前主体的申报历史。
                # 股类可以共享 CIK；输出仍保留各自的 ticker，与行情证券身份对齐。
                ciks = list(dict.fromkeys([*PREDECESSOR_CIKS.get(ticker, ()), cik]))
                company_frames, company_rejected = [], []
                complete = True
                for entity in ciks:
                    filename = f"CIK{entity}.json"
                    if filename not in names:
                        self.report["missing_files"].append(
                            {"ticker": ticker, "cik": entity}
                        )
                        complete = False
                        continue
                    # 直接读取目标成员，避免解压整个 ZIP；ZipFile.read 同时核验 CRC。
                    payload = json.loads(archive.read(filename))
                    # 缺少 facts 的损坏文件不能当成“合法但没有标准字段”的来源，
                    # 否则范围替换会清除该证券已有的财务历史。
                    if (
                        not isinstance(payload, dict)
                        or "cik" not in payload
                        or not isinstance(payload.get("facts"), dict)
                    ):
                        raise ValueError(f"无效 companyfacts 结构: {filename}")
                    if format_cik(payload["cik"]) != entity:
                        raise ValueError(f"CIK mismatch: {filename}")
                    # 先按候选科目缩小长表，单位、时点/期间及科目优先级由标准化器处理。
                    concepts = {
                        c
                        for f in selected_fields
                        for c in get_field_concepts(f, ticker)
                    }
                    raw = parse_company_facts(payload, concepts)
                    facts = standardize_facts(raw, ticker, selected_fields)
                    invalid = (
                        facts.period_end.gt(facts.filed)
                        | facts.period_start.gt(facts.period_end)
                        | ~np.isfinite(facts.value)
                    )
                    company_rejected.append(facts[invalid])
                    # 先隔离异常，再按单一 CIK 推导；不能跨主体相减累计值。
                    valid = facts[~invalid]
                    company_frames.append(derive_quarters(valid))
                if not complete:
                    continue  # 部分 CIK 不用于覆盖该 ticker 的历史
                frames.extend(company_frames)
                rejected.extend(company_rejected)
                completed.append(ticker)
        # 全部解析结束后才允许写库；来源错误不会留下已写入一半的结果。
        incomplete = self.report["missing_mappings"] or self.report["missing_files"]
        if incomplete and not allow_partial:
            raise ValueError(f"基本面来源不完整: {self.report}")
        out = self._combine(frames)
        self.quarantine = self._combine(rejected)
        # 缺字段与缺来源分开统计：某些行业没有一般企业的科目，不能自动补零。
        present = set(zip(out.ticker, out.field, strict=True))
        self.report["missing_fields"] = [
            {"ticker": t, "field": f}
            for t in completed
            for f in selected_fields
            if (t, f) not in present
        ]
        self.report.update(
            rows=len(out),
            tickers=int(out.ticker.nunique()),
            quarantined_rows=len(self.quarantine),
            derived_rows=int(out.derived.sum()),
        )
        if should_write and completed:
            save_fundamentals(self.db, out, self.quarantine, completed, selected_fields)
            self.report["written"] = True
        return out

    def prices(self, start, end=None, *, write: bool | None = None) -> pd.DataFrame:
        """从 Yahoo Finance 获取 universe 全部证券的日行情。

        Args:
            start: 起始交易日期，包含当日。
            end: 截止日期，不包含当日；None 使用数据源默认的最新可用日期。
            write: None 继承对象设置，False/True 单次覆盖。

        Returns:
            按 ticker/date 排序的行情长表：date、ticker、open、high、low、close、
            adj_close、volume。不自动复权，保留原始收盘价和复权收盘价。

        Raises:
            ValueError: end 不晚于 start，或写入时未配置 db。
            数据源或数据库异常继续传播，不伪装成成功结果。

        Notes:
            未返回行情的证券列入 report['missing_tickers']。入库按 ticker/date 更新，
            未返回的日期与证券保留旧值；load_prices 查询的日期范围则包含两端。
        """
        should_write = self.write if write is None else write
        if should_write and self.db is None:
            raise ValueError("write=True 需要 db")
        if end is not None and pd.Timestamp(start) >= pd.Timestamp(end):
            raise ValueError("end 必须晚于 start")
        self.report = {"kind": "prices", "written": False}
        out = get_prices(self._universe.ticker.tolist(), start=start, end=end)
        self.report.update(
            rows=len(out),
            missing_tickers=sorted(set(self._universe.ticker) - set(out.ticker)),
        )
        if should_write and not out.empty:
            save_prices(self.db, out)
            self.report["written"] = True
        return out

    def _combine(self, frames):
        """合并主体结果，按标准表主键解决冲突，保留不同文件的申报版本。

        冲突优先级：申报日较新、直接报告值、当前 CIK，最后用 CIK 排序稳定选择。
        空结果仍返回有明确列类型的标准表，避免 DuckDB 从空对象列猜出错误类型。
        """
        if not frames:
            # standardize_facts 提供明确的空表类型，便于 DuckDB 入库。
            return standardize_facts(
                parse_company_facts({"cik": 0, "facts": {}}), "EMPTY"
            )
        out = pd.concat(frames, ignore_index=True)
        current = self._universe.set_index("ticker").cik
        out["_current"] = out.cik.eq(out.ticker.map(current))
        out = out.sort_values(
            ["filed", "derived", "_current", "cik"],
            ascending=[False, True, False, False],
            kind="stable",
        )
        return (
            out.drop_duplicates(KEY)
            .drop(columns="_current")
            .sort_values(KEY, ignore_index=True)
        )
