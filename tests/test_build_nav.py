"""逐日组合简单收益的净值计算, 缺失收益后不恢复未知累计值。"""

import doctest
import importlib

import numpy as np
import pandas as pd
import pytest

from quanttoolskit.returns import build_nav


def returns(values, *, dtype=None, tz=None):
    return pd.Series(
        values,
        index=pd.date_range("2024-01-01", periods=len(values), tz=tz, name="date"),
        dtype=dtype,
        name="daily_return",
    )


def test_compounds_simple_returns_and_scales_capital_in_date_order():
    daily = returns([0.1, -0.05, 0.2])
    shuffled = daily.iloc[[2, 0, 1]]
    original = shuffled.copy(deep=True)
    pd.testing.assert_series_equal(
        build_nav(shuffled, 100.0),
        returns([110.0, 104.5, 125.4]).rename("nav"),
        check_freq=False,
    )
    pd.testing.assert_series_equal(shuffled, original)
    np.testing.assert_allclose(build_nav(daily), [1.1, 1.045, 1.254])


@pytest.mark.parametrize(
    "values,expected",
    [
        ([0.0, 0.1, -0.05], [1.0, 1.1, 1.045]),
        ([0.1, np.nan, 0.2], [1.1, np.nan, np.nan]),
        ([np.nan, 0.1], [np.nan, np.nan]),
        ([-1.0, 0.5, 0.0], [0.0, 0.0, 0.0]),
        ([-1.5, 0.1], [-0.5, -0.55]),
    ],
)
def test_first_day_missing_return_and_total_loss(values, expected):
    pd.testing.assert_series_equal(
        build_nav(returns(values)), returns(expected).rename("nav")
    )


@pytest.mark.parametrize("tz", [None, "Asia/Shanghai"])
@pytest.mark.parametrize("empty", [False, True])
def test_empty_nullable_series_and_timezone(tz, empty):
    daily = returns([] if empty else [0.1, pd.NA, 0.2], dtype="Float64", tz=tz)
    expected = returns([] if empty else [1.1, np.nan, np.nan], dtype=float, tz=tz)
    pd.testing.assert_series_equal(build_nav(daily), expected.rename("nav"))


def test_normalizes_index_name_and_does_not_add_missing_dates():
    daily = pd.Series(
        [0.1, 0.2], index=pd.DatetimeIndex(["2024-01-02", "2024-01-08"], name="day")
    )
    expected = pd.Series([1.1, 1.32], index=daily.index.rename("date"), name="nav")
    pd.testing.assert_series_equal(build_nav(daily), expected)


@pytest.mark.parametrize("capital", [np.int64(100), np.float64(100), 100])
def test_accepts_real_numeric_capital(capital):
    assert build_nav(returns([0.1]), capital).iloc[0] == pytest.approx(110.0)


@pytest.mark.parametrize("bad", [True, np.bool_(True), "100", None, 1j])
def test_rejects_non_real_capital(bad):
    with pytest.raises(TypeError, match="initial_capital"):
        build_nav(returns([0.1]), bad)


@pytest.mark.parametrize("bad", [0, -1, np.inf, -np.inf, np.nan])
def test_rejects_non_positive_or_non_finite_capital(bad):
    with pytest.raises(ValueError, match="有限正数"):
        build_nav(returns([0.1]), bad)


@pytest.mark.parametrize("bad", [pd.DataFrame({"r": [0.1]}), [0.1], None])
def test_rejects_non_series(bad):
    with pytest.raises(TypeError, match="Series"):
        build_nav(bad)


@pytest.mark.parametrize(
    "index",
    [
        pd.RangeIndex(2),
        pd.Index(["2024-01-01", "2024-01-02"]),
        pd.MultiIndex.from_product([pd.date_range("2024-01-01", periods=2), ["A"]]),
        pd.DatetimeIndex(["2024-01-01", "2024-01-01"]),
        pd.DatetimeIndex(["2024-01-01", pd.NaT]),
    ],
)
def test_rejects_invalid_or_ambiguous_date_index(index):
    with pytest.raises(ValueError, match="日期索引"):
        build_nav(pd.Series([0.1, 0.2], index=index))


@pytest.mark.parametrize("values", [[np.inf], [-np.inf], ["0.1"], [True], [1j]])
def test_rejects_non_finite_or_non_real_returns(values):
    with pytest.raises(ValueError, match="收益率"):
        build_nav(returns(values))


def test_docstring_examples_execute():
    result = doctest.testmod(importlib.import_module("quanttoolskit.returns"))
    assert result.failed == 0
    assert result.attempted > 0
