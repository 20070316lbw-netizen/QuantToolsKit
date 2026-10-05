"""准备固定成员快照，并用本地 SEC 名称/CIK 映射核对公司身份。

成员来源决定哪些证券属于 universe; SEC company_tickers.json 只提供公司关联，
不能替代指数成员名单。prepare_members 显式联网获取当前名单，load_members 只读取
本地快照。
两份来源中的 CIK 冲突时明确报错，不根据公司名称相似度猜测匹配。
"""

import json
from pathlib import Path

import pandas as pd

from .sources.wikipedia import fetch_current_constituents

# 已知的前身申报主体；当前 SEC ticker 映射通常只指向重组后的新主体。
# 这是人工登记的补充表，不保证覆盖全部改名、收购与控股重组。
PREDECESSOR_CIKS = {
    "GOOG": ("0001288776",),
    "GOOGL": ("0001288776",),
    "DIS": ("0001001039",),
    "XOM": ("0000034088",),
}


def normalize_sec_ticker(ticker: str) -> str:
    """去空白、转大写并把点号改为短横线，例如 BRK.B -> BRK-B。

    空值、空字符串或非字符串会抛 ValueError; 不根据 ticker 推断公司身份。
    """
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError(f"无效 ticker: {ticker!r}")
    return ticker.strip().upper().replace(".", "-")


def format_cik(cik: str | int) -> str:
    """将至多 10 位的数字 CIK 补成 10 位字符串，保留前导零。

    兼容表格读入时的整数浮点值（如 320193.0); 非整数、非 ASCII 数字或超长值
    会抛 ValueError。缺失 CIK 由调用方处理，不在这里转成字符串 'nan'。
    """
    if isinstance(cik, float) and cik.is_integer():
        cik = int(cik)
    digits = str(cik).strip()
    if not digits.isascii() or not digits.isdigit() or len(digits) > 10:
        raise ValueError(f"无效 CIK: {cik!r}")
    return digits.zfill(10)


def prepare_members(*, sec_tickers: str | Path | None = None) -> pd.DataFrame:
    """从 Wikipedia 获取当前成员，首次使用不需要准备成员文件。

    Args:
        sec_tickers: 可选的本地 SEC company_tickers.json，用于核对并补充 CIK 和
            SEC 公司名称。默认直接使用 Wikipedia 的 CIK，不请求或下载 SEC JSON。

    Returns:
        按 ticker 排序的当前成员 DataFrame，包含名称、行业、子行业、纳入日期及
        10 位 CIK。仅提供 sec_tickers 时追加 sec_cik/sec_title 核对列。
        attrs['source'] 为 'wikipedia'；不是历史成员资格或快照生效日期。

    Raises:
        ValueError: 成员结构或标识无效、SEC 映射重复，或非空 CIK 冲突。
        网页请求、解析及可选 SEC 文件读取错误继续传播。

    Notes:
        本函数显式联网，不写文件或数据库。需要复用快照时，可将返回值保存为
        CSV/Parquet，之后使用 load_members 读取；不从 date_added 推断历史成员区间。
    """
    members = normalize_members(fetch_current_constituents())
    members.attrs["source"] = "wikipedia"
    return _with_sec_mapping(members, sec_tickers)


def load_members(
    path: str | Path, *, sec_tickers: str | Path | None = None
) -> pd.DataFrame:
    """读取已有 CSV/Parquet 成员快照，不联网、不刷新成员资格。

    Args:
        path: 已有 .csv 或 .parquet 文件。至少包含 ticker/name；缺少 cik 列时
            创建空 CIK 列，方便作为共享 universe 使用。
        sec_tickers: 可选本地 SEC JSON，重新核对并补充身份；省略时保留快照中的
            CIK 和已有 SEC 信息，不要求另一个文件。

    Returns:
        规范化并按 ticker 排序的成员 DataFrame，attrs['source'] 为输入路径。

    Raises:
        ValueError: 不支持的文件格式、成员结构无效、ticker 重复或 CIK 冲突。
        文件不存在、CSV/Parquet/JSON 读取异常继续传播。

    Notes:
        多个股类共享 CIK 是合法的。该快照反映保存时的成员，不承诺是最新名单。
    """
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        members = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        members = pd.read_csv(
            path,
            dtype={"ticker": "string", "cik": "string", "sec_cik": "string"},
            keep_default_na=False,  # NA 等文本可能是证券代码，空 CIK 由规范化器处理。
        )
    else:
        raise ValueError("成员快照仅支持 CSV 或 Parquet")
    members = normalize_members(members)
    members.attrs["source"] = str(path)
    return _with_sec_mapping(members, sec_tickers)


def normalize_members(members: pd.DataFrame) -> pd.DataFrame:
    """规范证券标识及 CIK；保留其他成员信息，避免修改调用方的 DataFrame。"""
    members = members.copy()
    for column in ("ticker", "name"):
        if column not in members:
            raise ValueError(f"成员缺少 {column}")
    members["ticker"] = members.ticker.map(normalize_sec_ticker)
    if members.empty or members.ticker.duplicated().any():
        raise ValueError("成员快照为空或包含重复 ticker")
    if members.name.isna().any() or members.name.astype(str).str.strip().eq("").any():
        raise ValueError("成员名称不得为空")
    if "cik" not in members:
        members["cik"] = None
    members["cik"] = members.cik.map(
        lambda v: format_cik(v) if pd.notna(v) and str(v).strip() else None
    )
    return members.sort_values("ticker", ignore_index=True)


def _with_sec_mapping(
    members: pd.DataFrame, sec_tickers: str | Path | None
) -> pd.DataFrame:
    """可选身份核对，不用 SEC 名单替换指数成员，不静默覆盖冲突的 CIK。"""
    if sec_tickers is None:
        return members
    payload = json.loads(Path(sec_tickers).read_text())
    if not isinstance(payload, dict) or not payload:
        raise ValueError("SEC ticker 映射必须是非空 JSON 对象")
    sec = pd.DataFrame(
        [
            {
                "ticker": normalize_sec_ticker(r["ticker"]),
                "sec_cik": format_cik(r["cik_str"]),
                "sec_title": r["title"],
            }
            for r in payload.values()
        ]
    )
    if sec.ticker.duplicated().any():
        raise ValueError("SEC ticker 映射重复")
    # 快照可能已有 SEC 列；显式提供新 JSON 时才替换这些核对信息。
    out = members.drop(columns=["sec_cik", "sec_title"], errors="ignore").merge(
        sec, on="ticker", how="left", validate="one_to_one"
    )
    mismatch = out.cik.notna() & out.sec_cik.notna() & out.cik.ne(out.sec_cik)
    if mismatch.any():
        raise ValueError(
            f"Wikipedia/SEC CIK 冲突: {out.loc[mismatch, 'ticker'].tolist()}"
        )
    out["cik"] = out.cik.fillna(out.sec_cik)
    out.attrs = members.attrs.copy()
    return out.sort_values("ticker", ignore_index=True)
