"""按日期进行横截面分桶, 输出标准 DataFrame。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quanttoolskit.data.transfer_data import _validate_frame

N_QUANTILES: int = 5
N_VOL_GROUPS: int = 5


def _group_count(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} 必须是整数")
    if value < 1:
        raise ValueError(f"{name} 必须大于 0")


def _bucket(values: pd.Series, count: int) -> pd.Series:
    # 样本门槛按有效值计数；不足时保留全部键, 便于后续按索引对齐。
    valid = values.dropna()
    if len(valid) < count:
        return pd.Series(np.nan, index=values.index)
    # 重复边界只减少组数, 不按 ticker 顺序强行拆开相同分数。
    return pd.qcut(values, count, labels=False, duplicates="drop")


def _column(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        raise ValueError(f"缺少必要列: {[name]}")
    values = pd.to_numeric(df[name], errors="raise")
    if not np.isfinite(values.dropna()).all():
        raise ValueError(f"{name} 必须是有限数值")
    return values


def simple_bucket(
    df: pd.DataFrame, *, score_col: str = "score", n_quantiles: int = N_QUANTILES
) -> pd.DataFrame:
    """每日按分数进行横截面分位分桶。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 包含分数列；不修改输入。
        score_col: 分数列名, 默认 score；允许缺失值和数值字符串。
        n_quantiles: 每日分桶数量, 默认 5, 必须为正整数, 不接受布尔值。

    Returns:
        同输入键、按索引排序的单列 DataFrame, 列名 bucket。
        桶号从 0 开始, 分数越高桶号越高。每日有效样本不足时为 NaN；
        重复分位边界减少实际桶数, 全部分数相同时为 NaN, 不填补缺失值。

    Raises:
        TypeError: df 不是 DataFrame, 或 n_quantiles 不是整数。
        ValueError: 索引不符合契约、缺少分数列、分数非数值或非有限值,
            或 n_quantiles 小于 1。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.to_datetime(["2024-01-01"]), ["A", "B", "C", "D"]],
        ...     names=["date", "ticker"],
        ... )
        >>> signals = pd.DataFrame({"score": [1., 2., 3., 4.]}, index=index)
        >>> simple_bucket(signals, n_quantiles=2)["bucket"].tolist()
        [0, 0, 1, 1]
    """
    _validate_frame(df)
    _group_count(n_quantiles, "n_quantiles")
    score = _column(df, score_col).sort_index()
    if score.empty:
        return score.rename("bucket").to_frame()
    result = score.groupby(level="date", sort=False).transform(
        lambda values: _bucket(values, n_quantiles)
    )
    return result.rename("bucket").to_frame()


def vol_bucket(
    df: pd.DataFrame,
    *,
    score_col: str = "score",
    vol_col: str = "vol",
    n_quantiles: int = N_QUANTILES,
    n_vol_groups: int = N_VOL_GROUPS,
) -> pd.DataFrame:
    """每日先按波动率分层, 再在各层内按分数分桶。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 包含分数及波动率列。
        score_col: 分数列名, 默认 score。
        vol_col: 波动率列名, 默认 vol。两列均允许缺失值和数值字符串。
        n_quantiles: 每层内的分桶数量, 默认 5, 必须为正整数。
        n_vol_groups: 每日波动率分层数量, 默认 5, 必须为正整数。
            两种数量均不接受布尔值。

    Returns:
        同输入键、按索引排序的 DataFrame, 列为 vol_bucket 和 bucket。
        两种标签从 0 开始, 分别按波动率和分数递增。
        两列均有效的样本不足 n_vol_groups * n_quantiles 时, 当日全为 NaN。
        层内样本不足时仅 bucket 为 NaN。重复边界可能减少实际组数；
        不修改输入、不填补缺失值。

    Raises:
        TypeError: df 不是 DataFrame, 或分组数量不是整数。
        ValueError: 索引不符合契约、缺列、数值非有限或无法转换,
            或分组数量小于 1。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.to_datetime(["2024-01-01"]), ["A", "B", "C", "D"]],
        ...     names=["date", "ticker"],
        ... )
        >>> signals = pd.DataFrame(
        ...     {"score": [1., 2., 3., 4.], "vol": [1., 2., 3., 4.]}, index=index
        ... )
        >>> result = vol_bucket(signals, n_vol_groups=2, n_quantiles=2)
        >>> result["vol_bucket"].tolist()
        [0.0, 0.0, 1.0, 1.0]
        >>> result["bucket"].tolist()
        [0.0, 1.0, 0.0, 1.0]
    """
    _validate_frame(df)
    _group_count(n_quantiles, "n_quantiles")
    _group_count(n_vol_groups, "n_vol_groups")
    data = pd.DataFrame(
        {"score": _column(df, score_col), "vol": _column(df, vol_col)}
    ).sort_index()
    result = pd.DataFrame(np.nan, index=data.index, columns=["vol_bucket", "bucket"])
    for _, day in data.groupby(level="date", sort=False):
        # 两列共同有效才参与分层, 避免缺分数的证券改变其他证券的层号。
        eligible = day.dropna()
        if len(eligible) < n_vol_groups * n_quantiles:
            continue
        layers = _bucket(eligible["vol"], n_vol_groups)
        result.loc[layers.index, "vol_bucket"] = layers
        for _, layer in eligible.groupby(layers, sort=False):
            result.loc[layer.index, "bucket"] = _bucket(layer["score"], n_quantiles)
    return result
