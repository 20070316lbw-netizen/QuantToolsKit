"""Wikipedia 标普500页面的统一抓取与解析层。

页面上有两张我们关心的表:
    - 当前成分股名单   -> 解析成 CONSTITUENT_COLUMNS 这套 schema
    - 历次增删变动明细 -> 解析成 CHANGE_COLUMNS 这套 schema

当前名单供 prepare_members() 使用; 增删变动明细解析成 CHANGE_COLUMNS,
供后续维护历史成员资格区间, 现在包内还没有调用方。两套解析集中在这里,
避免两处各写一套解析逻辑、各用一套列名(此前一边叫 ticker 一边叫 symbol)。

解析上有意不依赖列的位置(iloc), 而是把表头规范化后按别名映射到我们自己的
列名。Wikipedia 随时可能插列、改表头、加脚注, 位置索引一旦错位是**静默**产
出错数据; 按名字匹配至少能在缺列时明确报错, 在多余列时自动忽略。

同理, 表也不按下标取(tables[0] / tables[1]), 而是扫描所有表、挑第一张能映射
出必需列的 —— 页面上方多个信息框表格的数量是会变的。
"""

from __future__ import annotations

import re
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd
from loguru import logger

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

#: 历次增删变动表所在的页面。这张表以前跟当前成分股表在同一页, 后来 Wikipedia
#: 把它拆到了这个独立词条里(截至这次核实, WIKI_URL 页面上已经完全没有这张表了,
#: 章节列表里也没有对应标题——不是改了表头/移了位置那么简单, 是整个搬家了)。
CHANGES_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"

#: 当前成分股表的输出 schema
CONSTITUENT_COLUMNS = ["ticker", "name", "sector", "sub_industry", "date_added", "cik"]

#: 增删变动表的输出 schema
CHANGE_COLUMNS = [
    "date",
    "added_ticker",
    "added_name",
    "removed_ticker",
    "removed_name",
    "reason",
]

# 规范化后的表头 -> 我们自己的列名。左边写多个别名是为了扛 Wikipedia 改表头。
_CONSTITUENT_ALIASES = {
    "symbol": "ticker",
    "ticker": "ticker",
    "security": "name",
    "company": "name",
    "gics_sector": "sector",
    "sector": "sector",
    "gics_sub_industry": "sub_industry",
    "sub_industry": "sub_industry",
    "date_added": "date_added",
    "date_first_added": "date_added",
    "cik": "cik",
}

_CHANGE_ALIASES = {
    "date": "date",
    # Wikipedia 现在把这一列标成 "Effective Date", 不是单纯的 "Date"
    "effective_date": "date",
    "added_ticker": "added_ticker",
    "added_symbol": "added_ticker",
    "added_security": "added_name",
    "added_company": "added_name",
    "removed_ticker": "removed_ticker",
    "removed_symbol": "removed_ticker",
    "removed_security": "removed_name",
    "removed_company": "removed_name",
    "reason": "reason",
}

# 认表用的必需列: 一张表只要能映射出这几列, 就认为是我们要找的那张。
_CONSTITUENT_REQUIRED = ("ticker", "name")
_CHANGE_REQUIRED = ("date", "added_ticker", "removed_ticker")

# "January 22, 2024" 这种英文长日期; Wikipedia 的日期单元格常混着脚注和换行。
_LONG_DATE_PATTERN = r"([A-Za-z]+\s+\d{1,2},\s+\d{4})"
# 脚注标记, 如 "AAPL[1]" / "2024-01-22[a]"
_FOOTNOTE_PATTERN = re.compile(r"\[[^\]]*\]")
# 表头规范化时用来把非字母数字压成下划线
_NON_WORD_PATTERN = re.compile(r"[^0-9a-z]+")
# read_html 给无表头列起的占位名
_PLACEHOLDER_PREFIX = "unnamed:"
# 空单元格在转成字符串后可能长这样, 一律当成缺失。读取时已关掉 pandas 的
# 自动 NA 识别(见 _read_tables), 这里是判断缺失的唯一位置。
_NULL_TOKENS = frozenset({"", "NAN", "NONE", "NA", "N/A", "NULL", "—", "–", "-"})
# ticker 列例外: "NA" 是合法证券代码(如 National Bank), 不能当成缺失丢弃。
# CSV 快照入口(load_members)用 keep_default_na=False 保留它, 两个入口口径保持一致。
_NULL_TICKER_TOKENS = _NULL_TOKENS - {"NA"}


def fetch_sp500_tables(
    url: str = WIKI_URL,
    changes_url: str = CHANGES_URL,
    timeout: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """抓取并解析 Wikipedia 上的当前成分股表与历次增删变动表。

    两张表现在分属两个不同的词条(见 CHANGES_URL 的注释), 所以要发两次请求;
    调用方一般不需要关心这个细节, 拿到的还是合并好的 (df_current, df_changes)。

    Args:
        url: 当前成分股表所在页面, 默认为官方标普500词条。
        changes_url: 历次增删变动表所在页面, 默认 CHANGES_URL。
        timeout: 单次 HTTP 请求超时秒数(两次请求各自计时)。

    Returns:
        (df_current, df_changes) 二元组:
            - df_current: 列为 CONSTITUENT_COLUMNS, 按 ticker 升序。
            - df_changes: 列为 CHANGE_COLUMNS, 按 date 降序(最近的在最前)。

    Raises:
        ValueError: 某张页面里找不到符合 schema 的表(通常意味着 Wikipedia 改版了)。
        urllib.error.URLError: 网络请求失败或返回非 2xx(HTTPError 是它的子类)。
        TimeoutError: 单次请求超过 timeout 秒。
    """
    current_tables = _read_tables(url, timeout)
    df_current = _parse_current(
        _pick_table(
            current_tables, _CONSTITUENT_ALIASES, _CONSTITUENT_REQUIRED, "当前成分股"
        )
    )

    change_tables = (
        current_tables if changes_url == url else _read_tables(changes_url, timeout)
    )
    df_changes = _parse_changes(
        _pick_table(change_tables, _CHANGE_ALIASES, _CHANGE_REQUIRED, "成分股变动")
    )
    logger.info(f"解析到 {len(df_current)} 只当前成分股, {len(df_changes)} 条增删记录")
    return df_current, df_changes


def fetch_current_constituents(url: str = WIKI_URL, timeout: int = 15) -> pd.DataFrame:
    """只抓当前成分股表。

    与 fetch_sp500_tables 一样只发一次 HTTP 请求, 区别是页面上没有变动表时
    不会报错 —— 调用方只要名单的话, 没必要被另一张表的结构变化拖累。

    Args:
        url: Wikipedia 页面地址。
        timeout: 单次 HTTP 请求超时秒数。

    Returns:
        DataFrame, 列为 CONSTITUENT_COLUMNS, 按 ticker 升序。
    """
    tables = _read_tables(url, timeout)
    return _parse_current(
        _pick_table(tables, _CONSTITUENT_ALIASES, _CONSTITUENT_REQUIRED, "当前成分股")
    )


def _read_tables(url: str, timeout: int) -> list[pd.DataFrame]:
    """拉页面并交给 pandas 解析出所有 <table>。"""
    logger.info(f"Fetching S&P 500 tables from {url}")
    request = Request(
        url, headers={"User-Agent": "QuantToolsKit/0.1 (S&P 500 research)"}
    )
    with urlopen(request, timeout=timeout) as response:
        html = response.read().decode("utf-8")
    # pandas 3.0 起 read_html 不再接受 HTML 字符串字面量(会被当成文件路径,
    # 报 FileNotFoundError), 必须包成 file-like 对象。
    # keep_default_na=False: 不让 pandas 把 "NA" 当成缺失值 —— 它是合法证券代码。
    # 缺失判断统一交给 _clean_text 的 _NULL_TOKENS, 与 load_members 读 CSV 时一致。
    tables = pd.read_html(StringIO(html), keep_default_na=False)
    if not tables:
        raise ValueError(f"{url} 页面里没有解析到任何表格")
    return tables


def _pick_table(
    tables: list[pd.DataFrame],
    aliases: dict[str, str],
    required: tuple[str, ...],
    label: str,
) -> pd.DataFrame:
    """在所有表里挑出第一张能映射出 required 全部列的表, 返回已重命名的副本。"""
    for index, table in enumerate(tables):
        renamed = _rename_columns(table, aliases)
        if all(column in renamed.columns for column in required):
            logger.debug(f"{label}表: 命中页面第 {index} 张表")
            return renamed

    raise ValueError(
        f"页面中找不到{label}表(需要能映射出列 {required}); "
        "Wikipedia 表结构可能已变更, 请检查 "
        "quanttoolskit/data/sources/wikipedia.py 的别名映射"
    )


def _rename_columns(table: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    """按别名表重命名列; 认不出来的列保留规范化后的原名。"""
    renamed = table.copy()
    renamed.columns = [
        aliases.get(label, label) for label in _flatten_columns(table.columns)
    ]
    # 重名列只保留第一个: 变动表里 "Added/Removed" 两组子表头重名时会撞车
    return renamed.loc[:, ~renamed.columns.duplicated()]


def _flatten_columns(columns: pd.Index) -> list[str]:
    """把(可能是多层的)表头压平成规范化的单层名字。

    变动表的表头是两层的: ("Added", "Ticker") -> "added_ticker"。pandas 对
    没跨列的表头会把上层标签重复一遍(("Date", "Date")), 或填 "Unnamed: 0_level_0",
    这两种噪音都要去掉。
    """
    flattened = []
    for column in columns:
        parts = column if isinstance(column, tuple) else (column,)
        kept: list[str] = []
        for part in parts:
            text = _normalize_label(part)
            if not text or text.startswith(_PLACEHOLDER_PREFIX):
                continue
            if kept and text == kept[-1]:  # ("Date", "Date") 这种重复
                continue
            kept.append(text)
        flattened.append("_".join(kept))
    return flattened


def _normalize_label(label: object) -> str:
    """表头规范化: 去脚注、转小写、非字母数字压成下划线。"""
    text = _FOOTNOTE_PATTERN.sub(" ", str(label)).strip().lower()
    return _NON_WORD_PATTERN.sub("_", text).strip("_")


def _parse_current(table: pd.DataFrame) -> pd.DataFrame:
    """把当前成分股表整理成 CONSTITUENT_COLUMNS schema。"""
    parsed = pd.DataFrame(index=table.index)
    parsed["ticker"] = _clean_ticker(table["ticker"])
    parsed["name"] = _clean_text(table["name"])
    for column in ("sector", "sub_industry", "cik"):
        parsed[column] = _clean_text(table[column]) if column in table else ""
    parsed["date_added"] = (
        _parse_dates(table["date_added"])
        if "date_added" in table
        else pd.Series(pd.NaT, index=table.index, dtype="datetime64[ns]")
    )

    parsed = parsed[parsed["ticker"] != ""]

    duplicated = parsed["ticker"].duplicated()
    if duplicated.any():
        logger.warning(
            f"当前成分股表有 {int(duplicated.sum())} 个重复代码, 只保留首次出现"
        )
        parsed = parsed[~duplicated]

    return parsed[CONSTITUENT_COLUMNS].sort_values("ticker").reset_index(drop=True)


def _parse_changes(table: pd.DataFrame) -> pd.DataFrame:
    """把增删变动表整理成 CHANGE_COLUMNS schema。"""
    parsed = pd.DataFrame(index=table.index)
    parsed["date"] = _parse_dates(table["date"])
    parsed["added_ticker"] = _clean_ticker(table["added_ticker"])
    parsed["removed_ticker"] = _clean_ticker(table["removed_ticker"])
    for column in ("added_name", "removed_name", "reason"):
        parsed[column] = _clean_text(table[column]) if column in table else ""

    unparsed = parsed["date"].isna()
    if unparsed.any():
        logger.warning(f"变动表有 {int(unparsed.sum())} 行日期无法解析, 已丢弃")
        parsed = parsed[~unparsed]

    # 两侧代码都为空的行对反推没有任何信息量(多是只改名/只改行业的记录)
    blank = (parsed["added_ticker"] == "") & (parsed["removed_ticker"] == "")
    if blank.any():
        logger.debug(f"变动表有 {int(blank.sum())} 行既无新增也无剔除, 已丢弃")
        parsed = parsed[~blank]

    return (
        parsed[CHANGE_COLUMNS]
        .sort_values("date", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def _clean_text(
    column: pd.Series, null_tokens: frozenset[str] = _NULL_TOKENS
) -> pd.Series:
    """单元格文本清洗: 去脚注、去首尾空白、空值统一成空字符串。

    null_tokens 默认按 _NULL_TOKENS 判断缺失; ticker 列传 _NULL_TICKER_TOKENS
    以保留 "NA" 这种同时是合法代码的取值。
    """
    text = (
        column.astype("string")
        .fillna("")
        .str.replace(_FOOTNOTE_PATTERN, "", regex=True)
        .str.strip()
    )
    return text.where(~text.str.upper().isin(null_tokens), "").astype("string")


def _clean_ticker(column: pd.Series) -> pd.Series:
    """代码清洗: 在 _clean_text 基础上转大写, 并把 "." 换成 "-"。

    BRK.B -> BRK-B, 与 yfinance/多数行情源的写法对齐。注意换点号必须放在空值
    判断之后, 否则 "-"(表示空)这类占位符会被误当成代码。
    """
    return (
        _clean_text(column, _NULL_TICKER_TOKENS)
        .str.upper()
        .str.replace(".", "-", regex=False)
    )


def _parse_dates(column: pd.Series) -> pd.Series:
    """日期列解析, 解析不出来的返回 NaT(由调用方决定丢弃还是保留)。"""
    text = _clean_text(column)
    # 先抓 "January 22, 2024" 这种长日期; 抓不到再让 pandas 直接猜原文
    # (覆盖 "2024-01-22" 等 ISO 写法)。
    extracted = text.str.extract(_LONG_DATE_PATTERN, expand=False)
    return pd.to_datetime(extracted.fillna(text), errors="coerce", format="mixed")
