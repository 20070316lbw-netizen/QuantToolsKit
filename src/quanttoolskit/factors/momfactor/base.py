"""在标准 [date, ticker] 价格表上计算窗口累计对数收益与动量。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.returns import log_returns


def cumulative_log_returns(
    df: pd.DataFrame,
    window: int,
    *,
    skip: int = 0,
    price_col: str = "adj_close",
) -> pd.Series:
    """计算 window 期累计对数收益率, 也可用于构造历史动量特征。

    先累计单期对数收益, 再按股票后移 skip 期。window=1、skip=0 时
    数值与 log_returns 相同；这是滚动窗口收益, 不从序列首日累计。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        window: 收益率窗口数量, 必填正整数, 不接受布尔值。
        skip: 跳过的最近记录数, 默认 0, 非负整数, 不接受布尔值。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。
            期数按每只股票实际记录计数, 不补齐交易日。

    Returns:
        排序后的 [date, ticker] Series,
        name 为 cumulative_log_return_{window}_skip_{skip}, 单位为累计对数收益率。
        完整窗口等于 log(price[t-skip]) - log(price[t-skip-window])。
        使用截至 t-skip 的历史价格, 不使用未来数据；不是百分数,
        可用 numpy.expm1 转成累计简单收益率。
        窗口内任一价格缺失时为 NaN, 即使两个端点都有价格；不填补价格。
        前 window+skip 条记录为 NaN, 空输入返回空 Series。

    Raises:
        TypeError: df 非 DataFrame, 或 window/skip 非整数。
        ValueError: 索引、价格不符合约定, window 非正数或 skip 为负数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=4), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., 2., 4., 8.]}, index=index)
        >>> cumulative_log_returns(prices, window=2, skip=1).iloc[-1].round(6)
        np.float64(1.386294)
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window <= 0:
        raise ValueError("window 必须大于 0")
    if isinstance(skip, bool) or not isinstance(skip, int):
        raise TypeError("skip 必须是整数")
    if skip < 0:
        raise ValueError("skip 必须大于等于 0")

    ret = log_returns(df=df, price_col=price_col)
    rolled = (
        ret.groupby(level="ticker", sort=False)
        .transform(
            lambda returns: returns.rolling(window=window, min_periods=window).sum()
        )
        .reindex(ret.index)
    )
    if skip:
        rolled = rolled.groupby(level="ticker", sort=False).shift(skip)
    return rolled.rename(f"cumulative_log_return_{window}_skip_{skip}").sort_index()


def momentum(
    df: pd.DataFrame,
    window: int,
    *,
    skip: int = 0,
    price_col: str = "adj_close",
) -> pd.Series:
    """兼容旧动量接口, 计算窗口累计对数收益率。

    新代码使用 cumulative_log_returns；这里保留原参数、计算口径和输出名称。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        window: 单期对数收益窗口数, 必填正整数, 不接受布尔值。
        skip: 跳过的最近交易记录数, 默认 0, 非负整数, 不接受布尔值。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。
            期数按每只证券自己的记录计数, 不补齐交易日。

    Returns:
        排序后的 [date, ticker] Series, name 为 momentum_{window}_skip_{skip},
        单位为累计对数收益率。数值与 cumulative_log_returns 相同。
        前 window+skip 条记录或窗口内价格缺失时为 NaN, 不填补价格。
        空输入返回同名空 Series, 可作为历史动量特征。

    Raises:
        TypeError: df 非 DataFrame, 或 window/skip 非整数。
        ValueError: 索引、价格不符合约定, window 非正数或 skip 为负数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., 2., 4.]}, index=index)
        >>> momentum(prices, window=2).iloc[-1].round(6)
        np.float64(1.386294)
    """
    result = cumulative_log_returns(df, window, skip=skip, price_col=price_col)
    return result.rename(f"momentum_{window}_skip_{skip}")
