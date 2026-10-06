"""期初等权买入、持仓不变的基准净值。"""

from __future__ import annotations

import math

import pandas as pd

from quanttoolskit.data.transfer_data import _validated_price


def buy_and_hold_nav(
    price: pd.DataFrame,
    initial_capital: float = 1.0,
    *,
    price_col: str = "close",
    portfolio_ticker: str = "BUY_AND_HOLD",
) -> pd.DataFrame:
    """首日等权买入, 之后份额固定, 计算逐日组合净值。

    Args:
        price: [date, ticker] MultiIndex 行情 DataFrame, 不接受价格宽表。
            首个日期有报价的证券构成固定成员池, 后续证券不加入。
        initial_capital: 期初资金, 默认 1.0, 必须为有限正数。
        price_col: 价格列名, 默认 close；可传 adj_close 采用复权价格。
            所选列必须为有限正数或缺失值, 所有证券须采用一致复权口径。
        portfolio_ticker: 输出中代表组合的 ticker, 默认 BUY_AND_HOLD,
            必须为非空字符串。

    Returns:
        [date, ticker] 索引的单列 DataFrame, 列名 nav。
        日期为输入中出现的日期, ticker 为 portfolio_ticker, 按索引排序。
        任一固定成员缺报价时当日为 NaN；报价恢复时可继续估值。
        空输入返回相同结构的空表。不计费用或单独的分红现金流。

    Raises:
        TypeError: price 不是 DataFrame, 或 initial_capital 非数值/为布尔值。
        ValueError: 行情索引、价格、期初资金或组合名称不符合约定,
            或首日没有任何有效价格。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.date_range("2024-01-01", periods=3), ["A", "B"]],
        ...     names=["date", "ticker"],
        ... )
        >>> prices = pd.DataFrame(
        ...     {"close": [100., 100., 200., 100., 100., 100.]}, index=index
        ... )
        >>> buy_and_hold_nav(prices, portfolio_ticker="BENCH")["nav"].tolist()
        [1.0, 1.5, 1.0]
    """
    if isinstance(initial_capital, bool) or not isinstance(
        initial_capital, (int, float)
    ):
        raise TypeError("initial_capital 必须是数值")
    if not math.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial_capital 必须是有限正数")
    if not isinstance(portfolio_ticker, str) or not portfolio_ticker.strip():
        raise ValueError("portfolio_ticker 必须是非空字符串")
    values = _validated_price(df=price, price_col=price_col)
    if not all(math.isfinite(value) for value in values.dropna()):
        raise ValueError(f"{price_col} 必须是有限数值")
    dates = values.index.get_level_values("date").unique()
    index = pd.MultiIndex.from_product(
        [dates, [portfolio_ticker]], names=["date", "ticker"]
    )
    if values.empty:
        return pd.DataFrame(index=index, columns=["nav"], dtype=float)
    wide = values.unstack("ticker").reindex(dates)
    # 首日价格确定买入份额；后续不再等权再平衡或扩大成员池。
    initial = wide.iloc[0].dropna()
    if initial.empty:
        raise ValueError("首个日期必须至少有一个有效价格")
    # skipna=False 保证缺报价不会被当成零收益, 也不会临时剔除持仓。
    nav = wide[initial.index].div(initial).mean(axis=1, skipna=False) * initial_capital
    return pd.DataFrame({"nav": nav.to_numpy()}, index=index)
