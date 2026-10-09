"""基于 (date, ticker) MultiIndex DataFrame 的波动率计算。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data.transfer_data import _validated_price


def history_vol(
    *,
    df: pd.DataFrame,
    window: int = 21,
    price_col: str = "close",
) -> pd.Series:
    """计算历史日简单收益率的滚动波动率。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        window: 窗口内收益率数量, 默认 21, 至少为 2 的整数, 不接受布尔值。
            期数按每只股票自己的交易记录计数。
        price_col: 价格列名, 默认 close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 volatility_{window}, 小数波动率。
        最近 window 个日简单收益率的样本标准差, ddof=1, 包含当天收益率。
        不年化、不填补价格；需 window+1 条有效价格记录才能首次计算。
        窗口不足或窗口内收益率缺失时为 NaN, 空输入返回空 Series。

    Raises:
        TypeError: df 非 DataFrame, 或 window 非整数。
        ValueError: 索引、价格不符合约定, 或 window 小于 2。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"close": [1., 2., 4.]}, index=index)
        >>> history_vol(df=prices, window=2).iloc[-1]
        np.float64(0.0)
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window < 2:
        raise ValueError("window 必须大于等于 2")

    price = _validated_price(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(1)
    daily_return = price / previous - 1

    volatility = (
        daily_return.groupby(level="ticker", sort=False)
        .transform(
            lambda returns: returns.rolling(
                window=window,
                min_periods=window,
            ).std(ddof=1)
        )
        .reindex(price.index)
    )

    return volatility.rename(f"volatility_{window}").sort_index()


def forward_volatility(
    *,
    df: pd.DataFrame,
    window: int = 21,
    gap: int = 1,
    price_col: str = "close",
) -> pd.Series:
    """计算未来持有区间内的波动率标签。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        window: 持有区间的单期收益率数量, 默认 21, 至少为 2 的整数。
        gap: 基准日到区间起点的记录数, 默认 1, 非负整数。
            期数按每只股票自己的交易记录计数, 均不接受布尔值。
        price_col: 价格列名, 默认 close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 forward_volatility_{window}_gap_{gap}。
        使用 price[t+gap] 至 price[t+gap+window] 的 window+1 个价格,
        计算 window 个日简单收益率的样本标准差, ddof=1, 小数波动率。
        不年化、不填补价格；未来记录不足或窗口收益率缺失时为 NaN。
        空输入返回空 Series。使用未来数据, 仅用于事后生成标签。

    Raises:
        TypeError: df 非 DataFrame, 或 window/gap 非整数。
        ValueError: 索引、价格不符合约定, window 小于 2 或 gap 为负数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"close": [1., 2., 4.]}, index=index)
        >>> forward_volatility(df=prices, window=2, gap=0).iloc[0]
        np.float64(0.0)
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window < 2:
        raise ValueError("window 必须大于等于 2")

    if isinstance(gap, bool) or not isinstance(gap, int):
        raise TypeError("gap 必须是整数")
    if gap < 0:
        raise ValueError("gap 必须大于等于 0")

    price = _validated_price(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(1)
    daily_return = price / previous - 1

    trailing_vol = (
        daily_return.groupby(level="ticker", sort=False)
        .transform(
            lambda returns: returns.rolling(
                window=window,
                min_periods=window,
            ).std(ddof=1)
        )
        .reindex(price.index)
    )

    # t + gap + window 处的滚动窗口,
    # 恰好包含 r[t + gap + 1] 到 r[t + gap + window]。
    forward_vol = trailing_vol.groupby(level="ticker", sort=False).shift(
        -(gap + window)
    )

    return forward_vol.rename(f"forward_volatility_{window}_gap_{gap}").sort_index()
