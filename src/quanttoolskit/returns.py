"""逐证券收益率计算, 以及单一组合逐日简单收益的净值累乘。"""

from __future__ import annotations

from numbers import Real

import numpy as np
import pandas as pd

from quanttoolskit.data.transfer_data import _validated_price


def future_returns(
    *,
    df: pd.DataFrame,
    n_periods: int = 5,
    gap: int = 1,
    price_col: str = "adj_close",
) -> pd.Series:
    """生成未来持有期的简单收益率标签。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        n_periods: 持有期数, 默认 5, 正整数, 按每只证券的交易记录计数。
        gap: 当天到入场的记录数, 默认 1, 非负整数;均不接受布尔值。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 forward_return_{n_periods}_gap_{gap}。
        值为 price[t+gap+n_periods] / price[t+gap] - 1, 单位为小数收益率。
        未来记录不足或端点缺失时为 NaN, 不填补价格;空输入返回空 Series。
        使用未来数据, 仅用于事后生成标签。

    Raises:
        TypeError: df 非 DataFrame, 或期数参数非整数。
        ValueError: 索引、价格不符合约定, n_periods 非正数或 gap 为负数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., 2., 4.]}, index=index)
        >>> future_returns(df=prices, n_periods=1, gap=0).iloc[:2].tolist()
        [1.0, 1.0]
    """
    if isinstance(n_periods, bool) or not isinstance(n_periods, int):
        raise TypeError("n_periods 必须是整数")
    if n_periods <= 0:
        raise ValueError("n_periods 必须大于 0")

    if isinstance(gap, bool) or not isinstance(gap, int):
        raise TypeError("gap 必须是整数")
    if gap < 0:
        raise ValueError("gap 必须大于等于 0")

    price = _validated_price(df=df, price_col=price_col)
    grouped = price.groupby(level="ticker", sort=False)

    entry = grouped.shift(-gap)
    exit_price = grouped.shift(-(gap + n_periods))

    return (
        (exit_price / entry - 1)
        .rename(f"forward_return_{n_periods}_gap_{gap}")
        .sort_index()
    )


def historical_return(
    *,
    df: pd.DataFrame,
    n_periods: int = 5,
    price_col: str = "adj_close",
) -> pd.Series:
    """计算截至基准日期的历史简单收益率。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        n_periods: 回看期数, 默认 5, 正整数, 不接受布尔值。
            按每只证券自己的交易记录计数, 不补齐交易日。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 historical_return_{n_periods}。
        值为 price[t] / price[t-n_periods] - 1, 单位为小数收益率。
        包含当天价格;历史记录不足或端点缺失时为 NaN, 不填补价格。
        空输入返回空 Series, 可用于历史特征。

    Raises:
        TypeError: df 非 DataFrame, 或 n_periods 非整数。
        ValueError: 索引、价格不符合约定, 或 n_periods 非正数。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., 2., 4.]}, index=index)
        >>> historical_return(df=prices, n_periods=1).iloc[1:].tolist()
        [1.0, 1.0]
    """
    if isinstance(n_periods, bool) or not isinstance(n_periods, int):
        raise TypeError("n_periods 必须是整数")
    if n_periods <= 0:
        raise ValueError("n_periods 必须大于 0")

    price = _validated_price(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(n_periods)

    return (price / previous - 1).rename(f"historical_return_{n_periods}").sort_index()


def log_returns(
    *,
    df: pd.DataFrame,
    price_col: str = "adj_close",
) -> pd.Series:
    """计算按 ticker 隔离的单期对数收益率。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 log_return, 单位为对数收益率。
        值为 log(price[t]) - log(price[t-1]);每只股票首行或相邻价格缺失时
        为 NaN, 不填补交易记录或价格。空输入返回空 Series。

    Raises:
        TypeError: df 非 DataFrame。
        ValueError: 索引、价格或所选列不符合约定。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=2), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., np.e]}, index=index)
        >>> log_returns(df=prices).iloc[1].round(6)
        np.float64(1.0)
    """
    price = _validated_price(df=df, price_col=price_col)
    log_price = np.log(price)
    previous = log_price.groupby(level="ticker", sort=False).shift(1)
    return (log_price - previous).rename("log_return").sort_index()


def build_nav(daily_returns: pd.Series, initial_capital: float = 1.0) -> pd.Series:
    """按日期顺序将单一组合的逐日简单收益率累乘成净值。

    Args:
        daily_returns: 单一组合收益率 Series, 使用非空且唯一的 DatetimeIndex
            日期键, 允许空 Series, 按日期排序后计算, 不接受证券 MultiIndex。
            值为实数小数简单收益率, 可缺失, 不接受无穷值或对数收益率。
            收益率可小于 -1, 此时按公式产生负净值, 不模拟强平或追加资金。
        initial_capital: 期初资金, 默认 1.0, 必须为有限正实数, 不接受布尔值。

    Returns:
        按日期排序的 DatetimeIndex Series, 索引名 date, Series.name 为 nav。
        nav[t] = initial_capital * prod(1 + daily_returns[s], s <= t),
        单位与期初资金一致, 保留输入日期、时区和精度, 不补齐交易日。
        首行已计入首日收益, 不自动添加期初值; 需要首日等于期初资金时,
        调用方须明确提供首日收益 0。缺失收益及之后的净值均为 NaN,
        不将未知收益当作 0; 空输入返回 float64 空 Series。

    Raises:
        TypeError: daily_returns 非 Series, 或 initial_capital 非实数/为布尔值。
        ValueError: 日期索引非 DatetimeIndex、含缺失或重复日期,
            收益率非实数数值或含无穷值, 或期初资金不是有限正数。

    Example:
        >>> dates = pd.date_range("2024-01-01", periods=3, name="date")
        >>> r = pd.Series([0.0, 0.1, -0.05], index=dates)
        >>> build_nav(r, initial_capital=100.0).round(2).tolist()
        [100.0, 110.0, 104.5]
    """
    if not isinstance(daily_returns, pd.Series):
        raise TypeError("daily_returns 必须是 Series")
    if isinstance(initial_capital, bool) or not isinstance(initial_capital, Real):
        raise TypeError("initial_capital 必须是实数")
    if not np.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial_capital 必须是有限正数")
    if (
        not isinstance(daily_returns.index, pd.DatetimeIndex)
        or daily_returns.index.hasnans
        or not daily_returns.index.is_unique
    ):
        raise ValueError("日期索引必须是非空且唯一的 DatetimeIndex 日期键")
    if (
        not pd.api.types.is_numeric_dtype(daily_returns.dtype)
        or pd.api.types.is_bool_dtype(daily_returns.dtype)
        or pd.api.types.is_complex_dtype(daily_returns.dtype)
    ):
        raise ValueError("收益率必须是实数数值或缺失值")
    values = daily_returns.sort_index().astype(float)
    if not np.isfinite(values.dropna()).all():
        raise ValueError("非缺失收益率必须是有限数值")
    # 某日收益未知后, 缺少完整累乘链, 之后也无法从收益率恢复净值。
    nav = initial_capital * (1.0 + values).cumprod(skipna=False)
    return nav.rename("nav").rename_axis("date")
