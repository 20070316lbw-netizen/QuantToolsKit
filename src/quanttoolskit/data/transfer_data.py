"""读取边界：将长表转换为标准 (date, ticker) MultiIndex DataFrame。"""

from __future__ import annotations

import pandas as pd


def to_date_ticker_frame(*, df: pd.DataFrame) -> pd.DataFrame:
    """保留所有数据列, 转换日期并按 (date, ticker) 排序；不修改输入。

    接受含 date/ticker 列的长表或已使用标准索引的数据框。
    键必须非空且唯一；不会聚合重复记录或填补缺失值。
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df 必须是 DataFrame")
    if not df.columns.is_unique:
        raise ValueError("数据列名必须唯一")
    if isinstance(df.index, pd.MultiIndex):
        if df.index.names != ["date", "ticker"]:
            raise ValueError("索引必须为 [date, ticker] MultiIndex")
        if {"date", "ticker"}.intersection(df.columns):
            raise ValueError("date 和 ticker 不能同时出现在索引和列中")
        data = df.reset_index()
    else:
        missing = {"date", "ticker"}.difference(df.columns)
        if missing:
            raise ValueError(f"缺少必要列: {sorted(missing)}")
        data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    if data[["date", "ticker"]].isna().any().any():
        raise ValueError("date 和 ticker 不能包含缺失值")
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("每个 (date, ticker) 必须只有一条记录")
    return data.set_index(["date", "ticker"]).sort_index()


def validate_prices(*, df: pd.DataFrame, price_col: str = "close") -> pd.DataFrame:
    """校验已转换行情的价格列, 返回副本；不转换索引、不填补缺失值。

    输入必须有 [date, ticker] MultiIndex, 日期层为 DatetimeIndex, 键非空且唯一。
    仅将所选价格列转换为数值并要求非缺失价格大于零, 保留其他列及索引顺序。
    """
    _validate_frame(df)
    data = df.copy()
    if price_col not in data.columns:
        raise ValueError(f"缺少必要列: {[price_col]}")
    data[price_col] = pd.to_numeric(data[price_col], errors="raise")
    if data[price_col].dropna().le(0).any():
        raise ValueError(f"{price_col} 中的非缺失价格必须大于 0")
    return data


def _validated_price(*, df: pd.DataFrame, price_col: str) -> pd.Series:
    """计算模块只接受标准索引, Series 仅作为内部计算中间值。"""
    return validate_prices(df=df, price_col=price_col).sort_index()[price_col]


def _validate_frame(df: pd.DataFrame) -> None:
    """校验计算输入的索引和列契约, 不转换或修改数据。"""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df 必须是 DataFrame")
    if not isinstance(df.index, pd.MultiIndex) or df.index.names != ["date", "ticker"]:
        raise ValueError(
            "请先用 to_date_ticker_frame 转换为 [date, ticker] MultiIndex DataFrame"
        )
    if not isinstance(df.index.get_level_values("date"), pd.DatetimeIndex):
        raise ValueError("date 索引必须为日期时间, 请先用 to_date_ticker_frame 转换")
    if df.index.to_frame(index=False).isna().any().any():
        raise ValueError("date 和 ticker 不能包含缺失值")
    if not df.index.is_unique:
        raise ValueError("每个 (date, ticker) 必须只有一条记录")
    if not df.columns.is_unique:
        raise ValueError("数据列名必须唯一")
    if {"date", "ticker"}.intersection(df.columns):
        raise ValueError("date 和 ticker 不能同时出现在索引和列中")
