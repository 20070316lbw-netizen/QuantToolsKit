"""共同交易日历和收益率净值示范; 运行: python examples/rebalance_nav.py。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data import to_date_ticker_frame
from quanttoolskit.rebalance import rebalance_dates, rebalance_dates_belong
from quanttoolskit.returns import build_nav, historical_return


def sample_prices() -> pd.DataFrame:
    """7 个交易日, B 缺少两天记录, A 的报价完整。"""
    dates = pd.bdate_range("2024-01-01", periods=7)
    raw = pd.DataFrame(
        {
            "date": list(dates) + list(dates.delete([1, 4])),
            "ticker": ["A"] * 7 + ["B"] * 5,
            "close": [100.0, 110.0, 99.0, 108.9, 108.9, 98.01, 107.811] + [50.0] * 5,
        }
    )
    return to_date_ticker_frame(df=raw)


if __name__ == "__main__":
    prices = sample_prices()
    # 使用所有证券共享的日期序列, B 的缺失记录不改变调仓节奏。
    calendar = prices.index.get_level_values("date").unique().sort_values()
    selected = rebalance_dates(calendar, freq=3)
    belong = rebalance_dates_belong(calendar, freq=3)
    print(selected)
    print(belong)

    # 演示单一持仓 A 的组合净值; 调仓日映射本身不生成权重或策略收益。
    daily_returns = historical_return(df=prices, n_periods=1, price_col="close").xs(
        "A", level="ticker"
    )
    # 首日定义为建仓时点, 尚未经历持有期, 因此显式设为 0, 不填补后续缺失。
    daily_returns.iloc[0] = 0.0
    nav = build_nav(daily_returns, initial_capital=100.0)
    print(nav)
