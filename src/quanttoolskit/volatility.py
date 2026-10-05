"""由逐日收益率衍生的波动率计算

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


def history_vol(
    *,
    df: pd.DataFrame,
    window: int = 21,
    price_col: str = "close",
) -> pd.Series:
    """计算历史日简单收益率的滚动波动率。

    输入：
        df: prices 表的查询结果，至少包含 date、ticker、price_col。
        window: 窗口内的日收益率数量，必须大于等于 2。
        price_col: 计算使用的价格列, 默认 close。

    口径：
        return[t] = price[t] / price[t - 1] - 1
        volatility[t] = 最近 window 个收益率的样本标准差 (ddof=1)

        窗口包含当天收益率，不年化，不填补缺失价格。
        需要 window + 1 条连续且价格有效的记录才能首次计算。

    输出：
        [date, ticker] MultiIndex Series, 小数波动率。
        窗口不足或窗口内收益率缺失时为 NaN。
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window < 2:
        raise ValueError("window 必须大于等于 2")

    price = transfer_prices(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(1)
    daily_return = price / previous - 1

    volatility = daily_return.groupby(level="ticker", sort=False).transform(
        lambda returns: returns.rolling(
            window=window,
            min_periods=window,
        ).std(ddof=1)
    )

    return volatility.rename(f"volatility_{window}").sort_index()


def forward_volatility(
    *,
    df: pd.DataFrame,
    window: int = 21,
    gap: int = 1,
    price_col: str = "close",
) -> pd.Series:
    """计算未来持有区间内的波动率标签

    Args:
        df: prices 表查询得到的长表
        window: 持有区间的期数, 也是单期收益率的数量，至少为 2
        gap: 基准日期到区间起点的期数, 至少为 0
        price_col: 使用的价格列, 默认 close

    口径：
        r[t] = price[t] / price[t - 1] - 1
        volatility[t] = std(
            r[t + gap + 1], ..., r[t + gap + window],
            ddof=1,
        )

        使用从 price[t + gap] 到 price[t + gap + window]
        的 window + 1 个价格，计算 window 个收益率的样本标准差。
        不年化，不填补缺失价格。

    Returns:
        [date, ticker] MultiIndex Series, 小数波动率。
        未来记录不足或窗口内收益率缺失时为 NaN。

    注意：
        期数按每只股票的交易记录计数。
        使用未来数据，只用于事后生成标签或评估预测。
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window < 2:
        raise ValueError("window 必须大于等于 2")

    if isinstance(gap, bool) or not isinstance(gap, int):
        raise TypeError("gap 必须是整数")
    if gap < 0:
        raise ValueError("gap 必须大于等于 0")

    price = transfer_prices(df=df, price_col=price_col)
    previous = price.groupby(level="ticker", sort=False).shift(1)
    daily_return = price / previous - 1

    trailing_vol = daily_return.groupby(level="ticker", sort=False).transform(
        lambda returns: returns.rolling(
            window=window,
            min_periods=window,
        ).std(ddof=1)
    )

    # t + gap + window 处的滚动窗口，
    # 恰好包含 r[t + gap + 1] 到 r[t + gap + window]。
    forward_vol = trailing_vol.groupby(level="ticker", sort=False).shift(
        -(gap + window)
    )

    return forward_vol.rename(f"forward_volatility_{window}_gap_{gap}").sort_index()
