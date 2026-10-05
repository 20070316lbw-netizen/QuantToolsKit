"""在标准 [date, ticker] 价格表上构造滚动对数动量。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.returns import log_returns


def momentum(
    df: pd.DataFrame,
    window: int,
    *,
    skip: int = 0,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """累计 window 个单期对数收益率，再按股票后移 skip 期。

    window 为正整数，skip 为非负整数，均不接受布尔值。
    期数按每只股票实际记录计数；不补齐交易日、不填补缺失价格。
    完整窗口的值为 log(price[t-skip] / price[t-skip-window])；
    窗口内任一价格缺失时为 NaN，即使两个端点都有价格。
    每只股票前 window + skip 条记录为 NaN。
    输出为排序后的单列 DataFrame，列名 momentum_{window}_skip_{skip}。
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window <= 0:
        raise ValueError("window 必须大于 0")
    if isinstance(skip, bool) or not isinstance(skip, int):
        raise TypeError("skip 必须是整数")
    if skip < 0:
        raise ValueError("skip 必须大于等于 0")

    ret = log_returns(df=df, price_col=price_col)["log_return"]
    rolled = (
        ret.groupby(level="ticker", sort=False)
        .transform(
            lambda returns: returns.rolling(window=window, min_periods=window).sum()
        )
        .reindex(ret.index)
    )
    if skip:
        rolled = rolled.groupby(level="ticker", sort=False).shift(skip)
    return rolled.rename(f"momentum_{window}_skip_{skip}").to_frame().sort_index()
