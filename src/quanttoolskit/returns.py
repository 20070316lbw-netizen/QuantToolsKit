"""逐日收益率的实现

我们的数据由 DuckDB 存储, 读出来默认就是长表, 所以我们不要求使用者转成宽表
尽限本文件统一约定:
    - 输入为 prices 表; 价格列叫做 price_col, 默认等于 close
    - 计算前再次手动按股票和日期排序, 避免调用者随机组合项目内各种函数导致有些内容没有
        排序而出错
    - 输出 ['date', 'ticker'] 为索引的 Series, 无法计算则为 NaN, 防止用于正儿八
        经的项目而项目本身不严谨

作者精力有限, 只能保证自己的使用不受项目影响, 不能保证别人能严谨使用本项目内代码
"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data.transfer_data import transfer_prices


def future_returns(
    *,
    df: pd.DataFrame,
    n_periods: int = 5,
    gap: int = 1,
    price_col: str = "close",
) -> pd.Series:
    """生成未来持有期的简单收益率标签

    输入：
        df: prices 表的查询结果，至少包含 date、ticker、price_col
        n_periods: 持有的期数, 必须大于 0。
        gap: 从今天往后隔几期，作为计算区间的起点。
        price_col: 计算使用的价格列, 默认 close。

    口径：
        label[t] = price[t + gap + n_periods] / price[t + gap] - 1

        默认在下一条交易记录的收盘价入场，持有 5 期后出场
        使用未来数据，只用于事后生成标签

    输出：
        [date, ticker] MultiIndex Series, 小数收益率
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

    price = transfer_prices(df=df, price_col=price_col)
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
    price_col: str = "close",
) -> pd.Series:
    """计算截至基准日期的历史简单收益率

    输入：
        df: prices 表的查询结果，至少包含 date、ticker、price_col
        n_periods: 回看期数, 必须大于 0
        price_col: 计算使用的价格列, 默认 close

    口径：
        return[t] = price[t] / price[t - n_periods] - 1

        包含当天价格，可用于动量、反转特征或历史表现统计。
        不填补缺失价格。

    输出：
        [date, ticker] MultiIndex Series, 小数收益率。
        历史记录不足或端点价格缺失时为 NaN。
    """
    if isinstance(n_periods, bool) or not isinstance(n_periods, int):
        raise TypeError("n_periods 必须是整数")
    if n_periods <= 0:
        raise ValueError("n_periods 必须大于 0")

    price = transfer_prices(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(n_periods)

    return (price / previous - 1).rename(f"historical_return_{n_periods}").sort_index()
