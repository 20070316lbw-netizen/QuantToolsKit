"""SEC 基本面的点时(point-in-time)读取: 从 fundamentals 表按申报日期做 as-of 查询。

fundamentals 表保存同一期间的所有申报版本(原始申报、后续作为比较期再次出现、
重述), 每个版本带申报日 filed。"在时点 t 能看到的数据"定义为 filed <= t 的版本中
最新申报的那个——这样回测时不会用到当时还没公布、或者后来才改过的数字。

filed 的精度只有日期。本接口提供按申报日期的 PIT; 盘中信号需另核验提交与公开时刻。

提供四个层次的查询:
    load_fundamentals        -- 原始版本行, 不做 as-of 取舍(核对/调试用)
    load_fundamentals_pit    -- 单个时点的快照
    load_fundamentals_panel  -- 多个时点(如每个调仓日)的快照面板
    load_fundamentals_ttm    -- 多点滚动四季度合计(TTM, 单季值 period_months=3)

以及增量更新辅助 load_latest_filed。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..connection import get_duckdb
from ..sources.sec.fields import FIELDS
from ..universe import normalize_sec_ticker

DateLike = str | date | datetime

FUNDAMENTAL_COLUMNS = [
    "ticker",
    "cik",
    "field",
    "concept",
    "unit",
    "period_start",
    "period_end",
    "period_months",
    "value",
    "fy",
    "fp",
    "form",
    "accn",
    "filed",
    "derived",
]
_PIT_COLUMNS = [
    "ticker",
    "field",
    "period_months",
    "period_start",
    "period_end",
    "value",
    "concept",
    "form",
    "accn",
    "filed",
    "derived",
]
_PANEL_COLUMNS = [
    "date",
    "ticker",
    "field",
    "period_months",
    "period_end",
    "value",
    "filed",
]
_TTM_COLUMNS = ["date", "ticker", "field", "period_end", "value"]
_LATEST_FILED_COLUMNS = ["ticker", "last_filed"]

# 多个版本在同一天申报时的先后: 报告值优先于推导值, 再按文件号
_VERSION_ORDER = "filed DESC, derived ASC, accn DESC"
# TTM 的四个单季截止日应跨约 9 个月(52/53 周财年会有几天出入)
_TTM_SPAN_DAYS = (250, 300)
# 逐个检查相邻季度, 不能只靠四个截止日的总跨度排除中间缺季或重叠期。
_TTM_QUARTER_GAP_DAYS = (70, 125)


def load_fundamentals(
    tickers: str | Sequence[str] | None = None,
    fields: str | Sequence[str] | None = None,
    start: DateLike | None = None,
    end: DateLike | None = None,
    *,
    period_months: int | Sequence[int] | None = None,
    filed_until: DateLike | None = None,
    db: str | Path,
) -> pd.DataFrame:
    """读取原始版本行(同一期间可能有多行), 不做 as-of 取舍。

    Args:
        tickers: 单个或多个 ticker, 统一大写和短横线; None 不限, 空序列不匹配。
        fields: 单个或多个标准字段(如 "revenue"), 默认不限。
        start: period_end 下限(含)。
        end: period_end 上限(含)。
        period_months: 0(时点)/3/6/9/12, 单个或多个, 默认不限。
        filed_until: 只要 filed <= 该日的版本。
        db: 数据库文件路径。

    Returns:
        DataFrame, 列为 FUNDAMENTAL_COLUMNS, 按 [ticker, field, period_end,
        period_months, filed] 升序。
    """
    _check_fields(fields)
    conditions, params = _filters(tickers, fields, period_months)
    for column, op, value in (
        ("period_end", ">=", start),
        ("period_end", "<=", end),
        ("filed", "<=", filed_until),
    ):
        if value is not None:
            conditions.append(f"{column} {op} ?")
            params.append(_date_str(value))

    sql = f"SELECT {', '.join(FUNDAMENTAL_COLUMNS)} FROM fundamentals"
    sql += _where(conditions)
    sql += " ORDER BY ticker, field, period_end, period_months, filed, accn"
    return _run(sql, params, db)


def load_fundamentals_pit(
    as_of: DateLike,
    tickers: str | Sequence[str] | None = None,
    fields: str | Sequence[str] | None = None,
    *,
    period_months: int | Sequence[int] | None = None,
    latest_only: bool = True,
    max_staleness_days: int | None = None,
    db: str | Path,
) -> pd.DataFrame:
    """某一时点能看到的基本面快照。

    Args:
        as_of: 时点, 只用 filed <= as_of 的版本。
        tickers / fields / period_months: 过滤条件, 同 load_fundamentals。
        latest_only: True 时每个 (ticker, field, period_months) 只返回最近一期;
            False 时返回截至 as_of 已公布的每一期(各取当时最新版本), 可用来算同比等。
        max_staleness_days: 最近一期的 period_end 距 as_of 超过这么多天就不返回,
            避免已退市、停止申报的公司一直沿用旧数据。默认 None 不过滤; 这里不同于
            load_fundamentals_panel 的 550, 因为本接口返回的是"当时可见的全套快照",
            是否容忍陈旧期间应由调用方决定, 不在默认值里悄悄改变查询结果。
        db: 数据库文件路径。

    Returns:
        DataFrame, 列为 [ticker, field, period_months, period_start, period_end, value,
        concept, form, accn, filed, derived], 按 [ticker, field, period_months,
        period_end] 升序。

    Example:
        >>> snap = load_fundamentals_pit(  # doctest: +SKIP
        ...     "2020-06-30", db="data/sp500.db",
        ...     fields=["total_equity", "net_income"], period_months=[0, 12]
        ... )
    """
    _check_fields(fields)
    conditions, params = _filters(tickers, fields, period_months)
    conditions.append("filed <= ?")
    params.append(_date_str(as_of))
    if max_staleness_days is not None:
        conditions.append("period_end >= CAST(? AS DATE) - CAST(? AS INTEGER)")
        params.extend([_date_str(as_of), int(max_staleness_days)])

    group = (
        "ticker, field, period_months"
        if latest_only
        else ("ticker, field, period_months, period_end")
    )
    sql = f"""
        SELECT {", ".join(_PIT_COLUMNS)}
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY {group} ORDER BY period_end DESC, {_VERSION_ORDER}
            ) AS rn
            FROM fundamentals{_where(conditions)}
        )
        WHERE rn = 1
        ORDER BY ticker, field, period_months, period_end
    """
    return _run(sql, params, db)


def load_fundamentals_panel(
    dates: Iterable[DateLike],
    tickers: str | Sequence[str] | None = None,
    fields: str | Sequence[str] | None = None,
    *,
    period_months: int | Sequence[int] | None = None,
    max_staleness_days: int | None = 550,
    db: str | Path,
) -> pd.DataFrame:
    """在一组时点(如调仓日)上分别取点时快照, 拼成长表面板。

    每个 (date, ticker, field, period_months) 取 date 当天已公布的最近一期, 同一期
    多个版本取 date 之前最新申报的那个。

    Args:
        dates: 时点序列(字符串、date、Timestamp、DatetimeIndex 都行)。
        tickers / fields / period_months: 过滤条件, 同 load_fundamentals。
        max_staleness_days: 最近一期的 period_end 距 date 超过这么多天就不返回
            (已退市、停止申报的公司不会一直沿用旧数据)。默认 550 天, 年度值(12 个月)
            在年报公布前最多也就旧 15 个月左右; None 表示不限。
        db: 数据库文件路径。

    Returns:
        DataFrame, 列为 [date, ticker, field, period_months, period_end, value, filed],
        按 [date, ticker, field, period_months] 升序。
    """
    _check_fields(fields)
    conditions, params = _filters(tickers, fields, period_months)
    join = "f.filed <= d.date"
    join_params: list[object] = []
    if max_staleness_days is not None:
        join += " AND f.period_end >= d.date - CAST(? AS INTEGER)"
        join_params.append(int(max_staleness_days))

    sql = f"""
        WITH d AS (SELECT DISTINCT CAST(date AS DATE) AS date FROM _pit_dates),
        f AS (SELECT * FROM fundamentals{_where(conditions)}),
        j AS (
            SELECT d.date, f.*, row_number() OVER (
                PARTITION BY d.date, f.ticker, f.field, f.period_months
                ORDER BY f.period_end DESC, {_VERSION_ORDER}
            ) AS rn
            FROM d JOIN f ON {join}
        )
        SELECT {", ".join(_PANEL_COLUMNS)} FROM j WHERE rn = 1
        ORDER BY date, ticker, field, period_months
    """
    return _run_with_dates(sql, [*params, *join_params], _PANEL_COLUMNS, dates, db)


def load_fundamentals_ttm(
    dates: Iterable[DateLike],
    tickers: str | Sequence[str] | None = None,
    fields: str | Sequence[str] | None = None,
    *,
    max_staleness_days: int | None = 200,
    db: str | Path,
) -> pd.DataFrame:
    """在一组时点上计算滚动四季度合计(TTM), 只适用于利润表/现金流量表的金额字段。

    对每个 date, 取当时已公布的最近 4 个单季(period_months=3, 含 sources 推导出的
    单季), 每个单季用 date 之前最新的版本, 求和。4 个单季必须齐全且首尾截止日相差
    约 9 个月(250~300 天), 每两个相邻截止日相差 70~125 天, 否则不返回。

    Args:
        dates: 时点序列。
        tickers / fields: 过滤条件。fields 应为可加字段(revenue、net_income、
            operating_cash_flow、capex 等), EPS/股数这类字段求和没有意义。
        max_staleness_days: 最近一个单季的 period_end 距 date 超过这么多天就不返回,
            默认 200 天; None 表示不限。
        db: 数据库文件路径。

    Returns:
        DataFrame, 列为 [date, ticker, field, period_end(最近一个单季的截止日), value],
        按 [date, ticker, field] 升序。
    """
    _check_fields(fields)
    additive = [name for name, spec in FIELDS.items() if spec.additive]
    selected = (
        additive
        if fields is None
        else ([fields] if isinstance(fields, str) else list(fields))
    )
    if set(selected) - set(additive):
        raise ValueError("TTM 仅支持可加金额字段, 不支持 EPS 或股数")
    if not selected:
        return pd.DataFrame(columns=_TTM_COLUMNS)
    conditions, params = _filters(tickers, selected, 3)
    join = "f.filed <= d.date"
    join_params: list[object] = []
    stale_filter = ""
    if max_staleness_days is not None:
        # 四个季度往前再多留 300 天, 保证最早那个季度也在窗口里
        join += " AND f.period_end >= d.date - CAST(? AS INTEGER)"
        join_params.append(int(max_staleness_days) + _TTM_SPAN_DAYS[1])
        stale_filter = " AND period_end >= date - CAST(? AS INTEGER)"

    sql = f"""
        WITH d AS (SELECT DISTINCT CAST(date AS DATE) AS date FROM _pit_dates),
        f AS (SELECT * FROM fundamentals{_where(conditions)}),
        v AS (
            SELECT d.date, f.ticker, f.field, f.period_end, f.value, row_number() OVER (
                PARTITION BY d.date, f.ticker, f.field, f.period_end
                ORDER BY {_VERSION_ORDER}
            ) AS rn
            FROM d JOIN f ON {join}
        ),
        q AS (
            SELECT date, ticker, field, period_end, value, row_number() OVER (
                PARTITION BY date, ticker, field ORDER BY period_end DESC
            ) AS k, lag(period_end) OVER (
                PARTITION BY date, ticker, field ORDER BY period_end DESC
            ) AS newer_end
            FROM v WHERE rn = 1
        ),
        agg AS (
            SELECT date, ticker, field,
                   max(period_end) AS period_end, min(period_end) AS first_end,
                   count(*) AS n, sum(value) AS value,
                   count(*) FILTER (
                       WHERE date_diff('day', period_end, newer_end) BETWEEN ? AND ?
                   ) AS consecutive_gaps
            FROM q WHERE k <= 4
            GROUP BY date, ticker, field
        )
        SELECT {", ".join(_TTM_COLUMNS)} FROM agg
        WHERE n = 4 AND consecutive_gaps = 3
          AND date_diff('day', first_end, period_end) BETWEEN ? AND ?{stale_filter}
        ORDER BY date, ticker, field
    """
    all_params = [*params, *join_params, *_TTM_QUARTER_GAP_DAYS, *_TTM_SPAN_DAYS]
    if max_staleness_days is not None:
        all_params.append(int(max_staleness_days))
    return _run_with_dates(sql, all_params, _TTM_COLUMNS, dates, db)


def load_latest_filed(
    tickers: str | Sequence[str] | None = None,
    *,
    db: str | Path,
) -> pd.DataFrame:
    """每只股票已入库的最近申报日, 供增量更新判断(比如只重抓超过一个季度没更新的)。

    Returns:
        DataFrame, 列为 [ticker, last_filed], 按 ticker 升序; 库里没有的股票不出现。
    """
    conditions, params = _filters(tickers, None, None)
    sql = "SELECT ticker, max(filed) AS last_filed FROM fundamentals"
    sql += _where(conditions) + " GROUP BY ticker ORDER BY ticker"
    return _run(sql, params, db)


# ---------------------------------------------------------------- helpers


def _filters(
    tickers: str | Sequence[str] | None,
    fields: str | Sequence[str] | None,
    period_months: int | Sequence[int] | None,
) -> tuple[list[str], list[object]]:
    conditions: list[str] = []
    params: list[object] = []
    for column, values in (
        ("ticker", tickers),
        ("field", fields),
        ("period_months", period_months),
    ):
        if values is None:
            continue
        # 空字符串沿用"不匹配"的历史语义, 不交给 normalize_sec_ticker 抛错。
        if isinstance(values, str) and not values.strip():
            conditions.append("FALSE")
            continue
        # is_scalar 覆盖 np.int64 这类非内建标量; 序列统一 list() 以接受迭代器。
        if pd.api.types.is_scalar(values):
            items = [values]
        else:
            items = list(values)
            if not items:
                conditions.append("FALSE")
                continue
        # DuckDB 无法绑定 numpy 标量(np.int64/np.str_ 等), 统一转成 Python 原生标量。
        items = [
            item.item() if isinstance(item, np.generic) else item for item in items
        ]
        if column == "ticker":
            items = [normalize_sec_ticker(ticker) for ticker in items]
        conditions.append(f"{column} IN ({', '.join(['?'] * len(items))})")
        params.extend(items)
    return conditions, params


def _check_fields(fields: str | Sequence[str] | None) -> None:
    """校验字段名, 与 normalize._check_fields 同口径, 不把拼错的字段当空结果。

    Raises:
        KeyError: fields 里有未定义的字段。
    """
    if fields is None:
        return
    items = [fields] if isinstance(fields, str) else list(fields)
    unknown = sorted({name for name in items if name not in FIELDS})
    if unknown:
        raise KeyError(f"未定义的基本面字段: {unknown}; 可选: {sorted(FIELDS)}")


def _where(conditions: list[str]) -> str:
    return " WHERE " + " AND ".join(conditions) if conditions else ""


def _date_str(value: DateLike) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _run(sql: str, params: list[object], db: str) -> pd.DataFrame:
    with get_duckdb(path=Path(db), read_only=True) as con:
        return con.execute(sql, params).df()


def _run_with_dates(
    sql: str,
    params: list[object],
    columns: list[str],
    dates: Iterable[DateLike],
    db: str,
) -> pd.DataFrame:
    date_frame = pd.DataFrame({"date": pd.to_datetime(list(dates)).normalize()})
    if date_frame.empty:
        return pd.DataFrame(columns=columns)
    with get_duckdb(path=Path(db), read_only=True) as con:
        con.register("_pit_dates", date_frame)
        return con.execute(sql, params).df()
