"""基于 (date, ticker) MultiIndex DataFrame 的收益率计算。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quanttoolskit.data.transfer_data import _validated_price


def future_returns(
    *,
    df: pd.DataFrame,
    n_periods: int = 5,
    gap: int = 1,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """生成未来持有期的简单收益率标签

    输入：
        df: 以 [date, ticker] 为索引的 DataFrame, 含 price_col 列
        n_periods: 持有的期数, 必须大于 0。
        gap: 从今天往后隔几期, 作为计算区间的起点。
        price_col: 计算使用的价格列, 默认 adj_close。

    口径：
        label[t] = price[t + gap + n_periods] / price[t + gap] - 1

        默认在下一条交易记录的收盘价入场, 持有 5 期后出场
        使用未来数据, 只用于事后生成标签

    输出：
        [date, ticker] MultiIndex DataFrame (单列)小数收益率
        未来记录不足或对应价格缺失时为 NaN
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
        .to_frame()
        .sort_index()
    )


def historical_return(
    *,
    df: pd.DataFrame,
    n_periods: int = 5,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """计算截至基准日期的历史简单收益率

    输入：
        df: 以 [date, ticker] 为索引的 DataFrame, 含 price_col 列
        n_periods: 回看期数, 必须大于 0
        price_col: 计算使用的价格列, 默认 adj_close

    口径：
        return[t] = price[t] / price[t - n_periods] - 1

        包含当天价格, 可用于动量、反转特征或历史表现统计。
        不填补缺失价格。

    输出：
        [date, ticker] MultiIndex DataFrame(单列)小数收益率。
        历史记录不足或端点价格缺失时为 NaN。
    """
    if isinstance(n_periods, bool) or not isinstance(n_periods, int):
        raise TypeError("n_periods 必须是整数")
    if n_periods <= 0:
        raise ValueError("n_periods 必须大于 0")

    price = _validated_price(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(n_periods)

    return (
        (price / previous - 1)
        .rename(f"historical_return_{n_periods}")
        .to_frame()
        .sort_index()
    )


def log_returns(
    *,
    df: pd.DataFrame,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """计算按 ticker 隔离的单期对数收益率。

    输入为 [date, ticker] MultiIndex DataFrame, 默认使用 adj_close。
    log_return[t] = log(price[t]) - log(price[t - 1])。
    输出为同索引的单列 DataFrame（log_return）, 按索引排序。
    每只股票首行或相邻任一价格缺失时为 NaN, 不填补交易记录或价格。
    """
    price = _validated_price(df=df, price_col=price_col)
    log_price = np.log(price)
    previous = log_price.groupby(level="ticker", sort=False).shift(1)
    return (log_price - previous).rename("log_return").to_frame().sort_index()
