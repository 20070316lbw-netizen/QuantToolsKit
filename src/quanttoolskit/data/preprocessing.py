"""数据预处理工具"""
from __future__ import annotations

import pandas as pd


def set_datetime_index(df: pd.DataFrame, date_col: str = 'date') -> pd.DataFrame:
    """
    将数据框的日期列转换为 DatetimeIndex, 并按时间顺序排序。
    (Time-series preprocessing: parse, set index, and sort chronologically.)
    
    Args:
        df: 原始数据框，必须包含 date_col 指定的列
        date_col: 日期列的列名，默认为 'date'
        
    Returns:
        pd.DataFrame: 处理后的数据框，索引为 DatetimeIndex
    """
    if date_col not in df.columns:
        raise ValueError(f"数据中找不到列: {date_col}")

    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()

    return df
