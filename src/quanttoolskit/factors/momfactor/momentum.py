"""按固定交易记录数近似月份的经典 12-1 动量。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.factors.momfactor.base import momentum


def momentum_12_1(
    *,
    df: pd.DataFrame,
    price_col: str = "adj_close",
    trading_days_per_month: int = 21,
) -> pd.Series:
    """计算过去 12 个月中剔除最近 1 个月的累计对数收益。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。
        trading_days_per_month: 每月近似记录数 m, 默认 21, 正整数,
            不接受布尔值。按证券记录计数, 不按日历月重采样。

    Returns:
        排序后的 [date, ticker] Series, name 为 mom_12_1, 单位为累计对数收益。
        窗口为 11*m, 后移 m；完整窗口值为 log(price[t-m]/price[t-12*m])。
        每只股票前 12*m 条记录或窗口内价格缺失时为 NaN, 不填补价格。
        空输入返回空 Series；跳过区间内价格不影响对应日期的因子值。

    Raises:
        TypeError: df 非 DataFrame, 或 trading_days_per_month 非整数。
        ValueError: 索引、价格不符合约定, 或 trading_days_per_month 非正数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=13), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame(
        ...     {"adj_close": [2.**i for i in range(13)]}, index=index
        ... )
        >>> momentum_12_1(df=prices, trading_days_per_month=1).iloc[-1].round(6)
        np.float64(7.624619)
    """
    if isinstance(trading_days_per_month, bool) or not isinstance(
        trading_days_per_month, int
    ):
        raise TypeError("trading_days_per_month 必须是整数")
    if trading_days_per_month <= 0:
        raise ValueError("trading_days_per_month 必须大于 0")
    result = momentum(
        df=df,
        window=11 * trading_days_per_month,
        skip=trading_days_per_month,
        price_col=price_col,
    )
    return result.rename("mom_12_1")
