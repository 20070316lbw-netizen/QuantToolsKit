"""累计对数收益取负的短期反转因子, 支持单期波动率缩放。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.factors.momfactor.base import cumulative_log_returns
from quanttoolskit.returns import log_returns


def reversal(
    df: pd.DataFrame,
    window: int = 21,
    *,
    skip: int = 0,
    vol_adjust: bool = True,
    price_col: str = "adj_close",
) -> pd.Series:
    """短期反转因子: 过去 window 期累计对数收益取负, 可按波动率缩放。

    Args:
        df: [date, ticker] MultiIndex DataFrame, 含 price_col 列, 键非空且唯一。
        window: 单期对数收益窗口数, 默认 21, 正整数, 不接受布尔值。
            vol_adjust=True 时至少为 2；按证券交易记录计数, 不补齐交易日。
        skip: 跳过的最近记录数, 默认 0, 非负整数, 不接受布尔值。
        vol_adjust: 默认 True, 必须为布尔值。是否除以同窗口内单期对数收益
            的样本标准差 ddof=1, 不年化, 不乘 sqrt(window)。
        price_col: 价格列名, 默认 adj_close, 非缺失价格须为正数。

    Returns:
        排序后的 [date, ticker] Series, name 为 reversal_{window}_skip_{skip},
        vol_adjust=True 时名称追加 _vol。未调整值为 window 期累计对数收益取负,
        使用截至 t-skip 的历史价格, 完整窗口等于
        log(price[t-skip-window]) - log(price[t-skip])；调整后为无量纲比值。
        下跌得到正值, 上涨得到负值。前 window+skip 条记录、窗口内价格缺失,
        或调整时样本标准差为零或缺失均为 NaN；不填补价格或交易记录。
        非常小的正标准差不截断, 因子值可能很大。空输入返回同名空 Series。

    Raises:
        TypeError: df 非 DataFrame, window/skip 非整数, 或 vol_adjust 非布尔值。
        ValueError: 索引、价格不符合约定, window 非正数, skip 为负数,
            或 vol_adjust=True 且 window 小于 2。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame({"adj_close": [1., 2., 8.]}, index=index)
        >>> reversal(prices, window=2, vol_adjust=False).iloc[-1].round(6)
        np.float64(-2.079442)
        >>> reversal(prices, window=2).iloc[-1].round(6)
        np.float64(-4.242641)
    """
    if isinstance(window, bool) or not isinstance(window, int):
        raise TypeError("window 必须是整数")
    if window <= 0:
        raise ValueError("window 必须大于 0")
    if isinstance(skip, bool) or not isinstance(skip, int):
        raise TypeError("skip 必须是整数")
    if skip < 0:
        raise ValueError("skip 必须大于等于 0")
    if not isinstance(vol_adjust, bool):
        raise TypeError("vol_adjust 必须是布尔值")
    if vol_adjust and window < 2:
        raise ValueError("vol_adjust=True 时 window 必须不小于 2")

    # 累计收益与动量共用窗口和缺失值口径, 先计算再对整个信号后移。
    signal = -cumulative_log_returns(df, window, price_col=price_col)

    if vol_adjust:
        ret = log_returns(df=df, price_col=price_col)
        vol = (
            ret.groupby(level="ticker", sort=False)
            .transform(
                lambda r: r.rolling(window=window, min_periods=window).std(ddof=1)
            )
            .reindex(ret.index)
        )
        # 零波动率没有可用的缩放尺度, 保留 NaN, 不产生无限大信号。
        signal = signal / vol.where(vol > 0)

    if skip:
        signal = signal.groupby(level="ticker", sort=False).shift(skip)

    name = f"reversal_{window}_skip_{skip}" + ("_vol" if vol_adjust else "")
    return signal.rename(name).sort_index()
