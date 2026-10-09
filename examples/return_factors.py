"""累计对数收益、反转、横截面标准化和分桶; 运行: python examples/return_factors.py。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data import to_date_ticker_frame
from quanttoolskit.factors import cumulative_log_returns, reversal
from quanttoolskit.indicators import zscore_by_date
from quanttoolskit.portfolio import simple_bucket


def sample_prices() -> pd.DataFrame:
    """3 条交易记录、2 只证券, A 上涨且 B 下跌。"""
    raw = pd.DataFrame(
        {
            "date": list(pd.date_range("2024-01-01", periods=3)) * 2,
            "ticker": ["A"] * 3 + ["B"] * 3,
            "adj_close": [1.0, 2.0, 8.0, 8.0, 4.0, 1.0],
        }
    )
    return to_date_ticker_frame(df=raw)


if __name__ == "__main__":
    prices = sample_prices()
    # 同一累计收益既可报告历史对数收益率, 也可作为动量特征。
    cumulative = cumulative_log_returns(prices, window=2)
    raw_reversal = reversal(prices, window=2, vol_adjust=False)
    adjusted_reversal = reversal(prices, window=2)
    print(pd.concat([cumulative, raw_reversal, adjusted_reversal], axis=1).round(6))
    # 同日证券之间标准化, 和因子自身窗口的波动率缩放含义不同。
    scores = zscore_by_date(adjusted_reversal.to_frame()).rename("score")
    buckets = simple_bucket(scores.to_frame(), n_quantiles=2)
    print(buckets)
