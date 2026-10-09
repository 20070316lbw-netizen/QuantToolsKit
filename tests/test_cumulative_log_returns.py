"""累计对数收益新名称与旧动量接口兼容性验证。"""

import doctest
import importlib

import numpy as np
import pandas as pd
import pytest

from quanttoolskit import log_returns
from quanttoolskit.factors import cumulative_log_returns, momentum


def frame(values):
    return pd.DataFrame(
        {"adj_close": values},
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-01", periods=len(values)), ["A"]],
            names=["date", "ticker"],
        ),
    )


@pytest.mark.parametrize("window,skip", [(1, 0), (2, 0), (2, 1), (3, 2)])
def test_new_name_formula_and_old_momentum_name_are_preserved(window, skip):
    prices = frame([100.0, 110.0, 99.0, 120.0, 90.0, 150.0, 125.0])
    result = cumulative_log_returns(prices, window=window, skip=skip)
    expected = [
        np.nan
        if t < window + skip
        else np.log(prices.iloc[t - skip, 0])
        - np.log(prices.iloc[t - skip - window, 0])
        for t in range(len(prices))
    ]
    name = f"cumulative_log_return_{window}_skip_{skip}"
    pd.testing.assert_series_equal(
        result, pd.Series(expected, index=prices.index, name=name)
    )
    old = momentum(prices, window, skip=skip)
    assert old.name == f"momentum_{window}_skip_{skip}"
    pd.testing.assert_series_equal(old.rename(name), result)


def test_single_period_matches_log_returns_and_missing_window_is_not_endpoint_only():
    prices = frame([100.0, np.nan, 110.0, 121.0, 145.2])
    pd.testing.assert_series_equal(
        cumulative_log_returns(prices, 1).rename("log_return"), log_returns(df=prices)
    )
    result = cumulative_log_returns(prices, 2)
    assert result.iloc[:4].isna().all()
    assert result.iloc[4] == pytest.approx(np.log(145.2 / 110.0))


def test_empty_named_series_and_public_exports():
    from quanttoolskit.factors.momfactor import cumulative_log_returns as package_fn
    from quanttoolskit.factors.momfactor.base import cumulative_log_returns as base_fn

    assert cumulative_log_returns is package_fn is base_fn
    result = cumulative_log_returns(frame([]), 2)
    assert isinstance(result, pd.Series) and result.empty
    assert result.name == "cumulative_log_return_2_skip_0"
    pd.testing.assert_index_equal(result.index, frame([]).index)


@pytest.mark.parametrize(
    "module_name",
    [
        "quanttoolskit.factors.momfactor.base",
        "quanttoolskit.factors.momfactor.momentum",
        "quanttoolskit.factors.reversal.base",
    ],
)
def test_public_docstring_examples_execute(module_name):
    result = doctest.testmod(importlib.import_module(module_name))
    assert result.failed == 0
    assert result.attempted > 0
