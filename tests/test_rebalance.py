"""调仓日使用共同交易日历, 保留时区并校验空输入。"""

import doctest
import importlib

import numpy as np
import pandas as pd
import pytest

from quanttoolskit.rebalance import rebalance_dates, rebalance_dates_belong


def test_irregular_calendar_is_sorted_deduplicated_and_mapped_at_boundaries():
    dates = pd.DatetimeIndex(
        ["2024-01-12", "2024-01-02", "2024-01-08", "2024-01-03", "2024-01-08"],
        name="date",
    )
    original = dates.copy()
    expected_dates = pd.DatetimeIndex(["2024-01-02", "2024-01-08"], name="date")
    pd.testing.assert_index_equal(rebalance_dates(dates, 2), expected_dates)
    expected = pd.Series(
        pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-08", "2024-01-08"]),
        index=pd.DatetimeIndex(
            ["2024-01-02", "2024-01-03", "2024-01-08", "2024-01-12"], name="date"
        ),
        name="rebalance_date",
    )
    pd.testing.assert_series_equal(rebalance_dates_belong(dates, 2), expected)
    pd.testing.assert_index_equal(dates, original)


@pytest.mark.parametrize("freq", [1, 3, 10, np.int64(3)])
def test_every_day_partial_last_interval_and_long_frequency(freq):
    dates = pd.bdate_range("2024-01-01", periods=7, name="date")
    pd.testing.assert_index_equal(rebalance_dates(dates, freq), dates[::freq])
    # 独立逐日确定最近已发生的调仓起点, 包括最后一个不完整区间。
    expected = pd.Series(
        [dates[(i // freq) * freq] for i in range(len(dates))],
        index=dates,
        name="rebalance_date",
    )
    pd.testing.assert_series_equal(rebalance_dates_belong(dates, freq), expected)


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("tz", [None, "Asia/Shanghai", "America/New_York"])
def test_empty_and_timezone_preserve_datetime_dtype(empty, tz):
    dates = pd.date_range("2024-03-08", periods=0 if empty else 5, tz=tz, name="date")
    selected = rebalance_dates(dates, 2)
    mapped = rebalance_dates_belong(dates, 2)
    pd.testing.assert_index_equal(selected, dates[::2])
    pd.testing.assert_index_equal(mapped.index, dates)
    assert mapped.dtype == dates.dtype
    assert mapped.name == "rebalance_date"
    if not empty:
        assert mapped.tolist() == [dates[0], dates[0], dates[2], dates[2], dates[4]]


@pytest.mark.parametrize("function", [rebalance_dates, rebalance_dates_belong])
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("bad", [0, -1, True, False, np.bool_(True), 1.5, "2", None])
def test_invalid_frequency_is_rejected_even_for_empty_calendar(function, empty, bad):
    dates = pd.date_range("2024-01-01", periods=0 if empty else 2)
    with pytest.raises(ValueError, match="freq 必须为正整数"):
        function(dates, bad)


@pytest.mark.parametrize("function", [rebalance_dates, rebalance_dates_belong])
def test_nat_is_rejected(function):
    with pytest.raises(ValueError, match="缺失"):
        function(pd.DatetimeIndex(["2024-01-01", pd.NaT]), 2)


@pytest.mark.parametrize("function", [rebalance_dates, rebalance_dates_belong])
@pytest.mark.parametrize("bad", [["2024-01-01"], pd.RangeIndex(2), None])
def test_calendar_requires_datetime_index(function, bad):
    with pytest.raises(TypeError, match="DatetimeIndex"):
        function(bad, 2)


def test_docstring_examples_execute():
    result = doctest.testmod(importlib.import_module("quanttoolskit.rebalance"))
    assert result.failed == 0
    assert result.attempted > 0
