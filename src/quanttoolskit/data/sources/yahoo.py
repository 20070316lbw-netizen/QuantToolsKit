"""价格数据抓取, 数据源: Yahoo Finance (通过 yfinance)

输出: 长表(long format), 每行是一个 (ticker, date) 的行情记录, 列固定为
[date, ticker, open, high, low, close, adj_close, volume]。

初步清洗:
    - 列名统一为小写 snake_case
    - date 转换为不带时区的时间戳, 便于跨数据源按日期 join
    - 数值列强制转为数值类型, 非法值变 NaN 而不是抛异常
    - 丢弃 close 整行缺失的记录(停牌/未上市导致的空行)
    - 单个 ticker 抓取失败只记录 warning 并跳过, 不影响批次里的其他 ticker

不做的事(留给下游仓库/使用方):
    - 复权方式的选择(auto_adjust 只是透传给 yfinance, 默认保留 close 与
      adj_close 两列, 具体用哪个由下游决定)
    - 缺口填补、重采样、收益率计算
    - 任何形式的本地存储/缓存
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd
from loguru import logger

DateLike = str | date | datetime

_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}

_OUTPUT_COLUMNS = [
    "date",
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
]
_NUMERIC_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


def get_prices(
    tickers: str | Sequence[str],
    start: DateLike,
    end: DateLike | None = None,
    *,
    interval: str = "1d",
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """抓取一批股票的历史行情, 返回清洗后的长表。

    Args:
        tickers: 单个 ticker 或 ticker 列表, 如 "AAPL" 或 ["AAPL", "MSFT"]。
        start: 起始日期(含), 如 "2020-01-01"。
        end: 结束日期(不含); 默认到今天(由 yfinance 决定)。
        interval: yfinance 支持的周期, 如 "1d"/"1wk"/"1mo"。
        auto_adjust: 透传给 yfinance; True 时 yfinance 直接返回复权价并可能
            丢弃 Adj Close 列, False(默认)保留原始 close 与 adj_close 两列。

    Returns:
        DataFrame, 列为 [date, ticker, open, high, low, close, adj_close, volume],
        按 (ticker, date) 排序。找不到数据时返回保留列结构的空 DataFrame。

    Raises:
        ValueError: tickers 为空。
    """
    ticker_list = [tickers] if isinstance(tickers, str) else list(tickers)
    if not ticker_list:
        raise ValueError("tickers 不能为空")

    logger.info(
        f"Fetching prices for {len(ticker_list)} ticker(s) "
        f"from {start} to {end or 'today'} (interval={interval})"
    )

    import yfinance as yf

    raw = yf.download(
        ticker_list,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=auto_adjust,
        group_by="ticker",
        progress=False,
        threads=True,
    )

    if raw is None or raw.empty:
        logger.warning("yfinance 未返回任何数据")
        return _empty_frame()

    frames = []
    if isinstance(raw.columns, pd.MultiIndex):
        # 多 ticker: 列是 (ticker, field) 两层
        available = set(raw.columns.get_level_values(0))
        for ticker in ticker_list:
            if ticker not in available:
                logger.warning(f"{ticker}: yfinance 无数据, 跳过")
                continue
            frames.append(_clean_single(raw[ticker].copy(), ticker, auto_adjust))  # type: ignore
    else:
        # 单 ticker: 列是单层
        if len(ticker_list) != 1:
            raise ValueError("多证券行情缺少 ticker 列层级，无法确认证券身份")
        frames.append(_clean_single(raw.copy(), ticker_list[0], auto_adjust))

    if not frames:
        return _empty_frame()

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
    return result


def _clean_single(
    df: pd.DataFrame, ticker: str, auto_adjust: bool = False
) -> pd.DataFrame:
    """把 yfinance 单 ticker 的宽表整理成标准长表 schema。"""
    df = df.rename(columns=_COLUMN_MAP)
    df = df.reset_index().rename(columns={"Date": "date", "Datetime": "date"})
    df["date"] = pd.to_datetime(df["date"])
    if df["date"].dt.tz is not None:
        df["date"] = df["date"].dt.tz_localize(None)
    df["ticker"] = ticker

    # 只有数据源明确已复权时，close 才能当作 adj_close；缺少复权价时保留空值。
    if "adj_close" not in df.columns and auto_adjust:
        df["adj_close"] = df.get("close")

    for col in _OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[_OUTPUT_COLUMNS]

    df[_NUMERIC_COLUMNS] = df[_NUMERIC_COLUMNS].apply(pd.to_numeric, errors="coerce")

    before = len(df)
    df = df.dropna(subset=["close"])
    dropped = before - len(df)
    if dropped:
        logger.debug(f"{ticker}: 丢弃 {dropped} 行 close 缺失的记录")

    return df


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_OUTPUT_COLUMNS)
