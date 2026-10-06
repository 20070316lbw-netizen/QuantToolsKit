"""按日期逐列计算因子面板的横截面标准分数。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quanttoolskit.data.transfer_data import _validate_frame


def zscore_by_date(df: pd.DataFrame, *, date_level: str = "date") -> pd.DataFrame:
    """逐日、逐列计算 z = (值 - 当日均值) / 当日样本标准差。

    Args:
        df: [date, ticker] MultiIndex 因子 DataFrame, 一列一个因子。
            允许缺失值及可转换的数值字符串, 不修改输入。
        date_level: 日期层名, 默认 date; 为遵循项目契约, 只接受 date。

    Returns:
        与输入键、列相同且按索引排序的 DataFrame, 数值无量纲。
        每列在每个日期内独立计算, 标准差采用 ddof=1（样本标准差）。
        均值、标准差仅使用非缺失值；原缺失值保留为 NaN。
        标准差为 0、有效样本少于 2 或全缺失时, 当日该因子全为 NaN。
        不补记录、不截尾, 也不对不同因子求平均或合成分数。

    Raises:
        TypeError: df 不是 DataFrame。
        ValueError: 索引或列不符合契约、date_level 不是 date,
            或因子含无法转换的非数值/无穷值。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.to_datetime(["2024-01-01"]), ["A", "B", "C"]],
        ...     names=["date", "ticker"],
        ... )
        >>> factors = pd.DataFrame({"f1": [1., 2., 3.]}, index=index)
        >>> zscore_by_date(factors)["f1"].tolist()
        [-1.0, 0.0, 1.0]
    """
    _validate_frame(df)
    if date_level != "date":
        raise ValueError("date_level 必须为 date")
    data = df.apply(pd.to_numeric, errors="raise").astype(float).sort_index()
    if np.isinf(data.to_numpy()).any():
        raise ValueError("因子必须是有限数值或缺失值")
    if data.empty:
        return data
    grouped = data.groupby(level="date", sort=False)
    mean = grouped.transform("mean")
    std = grouped.transform("std")
    # 常数截面没有可定义的标准分数；掩蔽零分母, 不人为赋值为 0。
    return (data - mean) / std.where(std.ne(0))
