"""按固定交易记录数近似月份的经典 12-1 动量。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.factors.momfactor.base import momentum


def momentum_12_1(
    *,
    df: pd.DataFrame,
    price_col: str = "adj_close",
    trading_days_per_month: int = 21,
) -> pd.DataFrame:
    """计算过去 12 个月中剔除最近 1 个月的累计对数收益。

    每月近似为 m=trading_days_per_month 条记录, 不按日历月重采样。
    窗口为 11*m, 后移 m; 有效完整窗口值为 log(price[t-m]/price[t-12*m])。
    m 必须为正整数且不接受布尔值；缺失值口径见 momentum。
    输出为同索引的单列 DataFrame(mom_12_1)按索引排序。
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
    result.columns = ["mom_12_1"]
    return result
