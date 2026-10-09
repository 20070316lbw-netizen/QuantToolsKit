"""验证读取转换与计算接口之间的数据结构契约。"""

import pandas as pd
import pytest

from quanttoolskit import (
    forward_volatility,
    future_returns,
    historical_return,
    history_vol,
    log_returns,
)
from quanttoolskit.data import to_date_ticker_frame
from quanttoolskit.factors import cumulative_log_returns, momentum_12_1, reversal

FUNCTIONS = [
    future_returns,
    historical_return,
    history_vol,
    forward_volatility,
    log_returns,
    momentum_12_1,
    lambda **kwargs: cumulative_log_returns(window=2, **kwargs),
    reversal,
]


@pytest.mark.parametrize("function", FUNCTIONS)
def test_calculations_require_multiindex(function):
    raw = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": [1]})
    with pytest.raises(ValueError, match="to_date_ticker_frame"):
        function(df=raw)


@pytest.mark.parametrize("function", FUNCTIONS)
def test_empty_calculation_retains_named_series_schema(function):
    raw = pd.DataFrame(columns=["date", "ticker", "close"])
    result = function(df=to_date_ticker_frame(df=raw), price_col="close")
    assert isinstance(result, pd.Series)
    assert result.empty
    assert isinstance(result.name, str) and result.name
    assert result.index.names == ["date", "ticker"]


def test_features_join_and_input_is_unchanged():
    raw = pd.DataFrame(
        {
            "date": list(pd.date_range("2024-01-01", periods=8)) * 2,
            "ticker": ["A"] * 8 + ["B"] * 8,
            "close": list(range(1, 9)) + list(range(10, 18)),
            "volume": 100,
        }
    ).sample(frac=1, random_state=7)
    prices = to_date_ticker_frame(df=raw)
    before = prices.copy(deep=True)
    results = [function(df=prices, price_col="close") for function in FUNCTIONS]
    for result in results:
        assert isinstance(result, pd.Series)
        assert result.index.is_unique and result.index.is_monotonic_increasing
    features = pd.concat(results, axis=1)
    assert features.shape == (16, len(FUNCTIONS))
    assert features.index.equals(prices.index)
    assert features.columns.is_unique
    pd.testing.assert_frame_equal(
        prices.join(results[0]).drop(columns=results[0].name), prices
    )
    pd.testing.assert_frame_equal(prices, before)
