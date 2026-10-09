"""横截面分桶和固定持仓基准的数值与数据契约回归测试。"""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from quanttoolskit.data.transfer_data import to_date_ticker_frame
from quanttoolskit.performance import buy_and_hold_nav
from quanttoolskit.portfolio import simple_bucket, vol_bucket


def frame(rows, columns):
    return to_date_ticker_frame(
        df=pd.DataFrame(rows, columns=["date", "ticker", *columns])
    )


def test_simple_bucket_separates_dates_preserves_missing_and_input():
    data = frame(
        [
            ("2024-01-01", t, v)
            for t, v in zip("ABCDE", [1, 2, 3, 4, np.nan], strict=True)
        ]
        + [("2024-01-02", "A", 100)],
        ["score"],
    )
    original = data.copy(deep=True)
    result = simple_bucket(data.iloc[::-1], n_quantiles=2)
    assert result.index.equals(data.index)
    assert isinstance(result, pd.Series)
    assert result.name == "bucket"
    assert result.iloc[:4].tolist() == [0, 0, 1, 1]
    assert result.iloc[4:].isna().all()
    assert_frame_equal(data, original)


def test_vol_bucket_uses_independent_group_counts_and_returns_layers():
    data = frame([("2024-01-01", str(i), 6 - i, i) for i in range(6)], ["score", "vol"])
    result = vol_bucket(data, n_vol_groups=2, n_quantiles=3)
    assert result["vol_bucket"].tolist() == [0, 0, 0, 1, 1, 1]
    assert result["bucket"].tolist() == [2, 1, 0, 2, 1, 0]
    assert result.index.equals(data.index)


def test_vol_bucket_insufficient_layer_ties_missing_and_date_isolation():
    data = frame(
        [("2024-01-01", str(i), i, v) for i, v in enumerate([1, 1, 2, 2, 3, np.nan])]
        + [("2024-01-02", "A", 1, 1)],
        ["score", "vol"],
    )
    result = vol_bucket(data, n_vol_groups=2, n_quantiles=2)
    assert result.iloc[:4]["bucket"].notna().all()
    assert pd.isna(result.iloc[4]["bucket"])
    assert result.iloc[5:].isna().all().all()
    assert simple_bucket(data.assign(score=1), n_quantiles=2).isna().all()


def test_buy_and_hold_fixed_shares_differs_from_daily_rebalancing():
    data = frame(
        [
            ("2024-01-01", "A", 100),
            ("2024-01-01", "B", 100),
            ("2024-01-02", "A", 200),
            ("2024-01-02", "B", 100),
            ("2024-01-03", "A", 100),
            ("2024-01-03", "B", 100),
        ],
        ["close"],
    )
    original = data.copy(deep=True)
    result = buy_and_hold_nav(data.iloc[::-1], 10)
    expected = pd.Series(
        [10.0, 15.0, 10.0],
        index=pd.date_range("2024-01-01", periods=3, name="date"),
        name="nav",
    )
    assert isinstance(result.index, pd.DatetimeIndex)
    assert_series_equal(result, expected, check_freq=False, check_index_type=False)
    assert_frame_equal(data, original)


def test_benchmark_missing_prices_stays_missing_and_new_members_are_excluded():
    data = frame(
        [
            ("2024-01-01", "A", 10),
            ("2024-01-01", "B", 20),
            ("2024-01-02", "A", 20),
            ("2024-01-02", "C", 999),
            ("2024-01-03", "A", np.nan),
            ("2024-01-03", "B", 20),
            ("2024-01-04", "A", 20),
            ("2024-01-04", "B", 20),
        ],
        ["adj_close"],
    )
    result = buy_and_hold_nav(data, price_col="adj_close")
    assert result.iloc[0] == 1
    assert result.iloc[1:3].isna().all()
    assert result.iloc[3] == 1.5


@pytest.mark.parametrize("func", [simple_bucket, vol_bucket, buy_and_hold_nav])
def test_input_contract_and_empty_frames(func):
    data = frame([], ["score", "vol", "close"])
    result = func(data)
    assert isinstance(result, pd.DataFrame if func is vol_bucket else pd.Series)
    assert result.empty
    if func is buy_and_hold_nav:
        assert isinstance(result.index, pd.DatetimeIndex)
        assert result.index.name == "date" and result.name == "nav"
    else:
        assert result.index.equals(data.index)
        if func is simple_bucket:
            assert result.name == "bucket"
        else:
            assert result.columns.tolist() == ["vol_bucket", "bucket"]
    with pytest.raises(TypeError):
        func(pd.Series(dtype=float))
    with pytest.raises(ValueError):
        func(data.reset_index())
    duplicate = frame([("2024-01-01", "A", 1, 1, 1)], ["score", "vol", "close"])
    with pytest.raises(ValueError):
        func(pd.concat([duplicate, duplicate]))


@pytest.mark.parametrize(
    "bad,error", [(True, TypeError), (1.5, TypeError), (0, ValueError)]
)
def test_invalid_group_counts(bad, error):
    data = frame([], ["score", "vol"])
    with pytest.raises(error):
        simple_bucket(data, n_quantiles=bad)
    with pytest.raises(error):
        vol_bucket(data, n_vol_groups=bad)


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan")])
def test_invalid_capital(bad):
    with pytest.raises(ValueError):
        buy_and_hold_nav(frame([], ["close"]), bad)


def test_missing_columns_nonfinite_and_missing_initial_prices():
    data = frame([("2024-01-01", "A", np.nan)], ["close"])
    with pytest.raises(ValueError):
        buy_and_hold_nav(data)
    with pytest.raises(ValueError):
        simple_bucket(data)
    with pytest.raises(ValueError):
        vol_bucket(data.assign(score=1))
    with pytest.raises(ValueError):
        buy_and_hold_nav(data.assign(close=np.inf))
    with pytest.raises(ValueError):
        simple_bucket(data.assign(score=np.inf))
    with pytest.raises(TypeError):
        buy_and_hold_nav(data, True)
