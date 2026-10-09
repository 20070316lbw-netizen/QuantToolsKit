"""反转因子的公式、样本边界与公开接口回归测试。"""

import numpy as np
import pandas as pd
import pytest

from quanttoolskit.factors import cumulative_log_returns, reversal


def frame(values, ticker="A"):
    return pd.DataFrame(
        {"adj_close": values},
        index=pd.MultiIndex.from_product(
            [pd.date_range("2024-01-01", periods=len(values)), [ticker]],
            names=["date", "ticker"],
        ),
    )


def test_reversal_uses_series_log_returns_and_sample_std():
    prices = frame([1.0, 2.0, 8.0])
    result = reversal(prices, window=2)
    expected = pd.Series(
        [np.nan, np.nan, -3 * np.sqrt(2)],
        index=prices.index,
        name="reversal_2_skip_0_vol",
    )
    pd.testing.assert_series_equal(result, expected)


@pytest.mark.parametrize("vol_adjust", [False, True])
@pytest.mark.parametrize("skip", [0, 1, 3])
def test_formula_direction_and_skip_uses_same_historical_window(vol_adjust, skip):
    values = [100.0, 110.0, 99.0, 120.0, 90.0, 150.0, 125.0]
    prices = frame(values)
    returns = np.diff(np.log(values))
    expected = []
    for t in range(len(values)):
        end = t - skip
        if end < 2:
            expected.append(np.nan)
            continue
        sample = returns[end - 2 : end]
        value = -sample.sum()
        if vol_adjust:
            value /= sample.std(ddof=1)
        expected.append(value)
    result = reversal(prices, window=2, skip=skip, vol_adjust=vol_adjust)
    name = f"reversal_2_skip_{skip}" + ("_vol" if vol_adjust else "")
    pd.testing.assert_series_equal(
        result, pd.Series(expected, index=prices.index, name=name)
    )
    if not vol_adjust:
        cumulative = cumulative_log_returns(prices, 2, skip=skip)
        pd.testing.assert_series_equal(result, (-cumulative).rename(name))


@pytest.mark.parametrize("vol_adjust", [False, True])
def test_missing_window_recovers_and_skipped_prices_do_not_participate(vol_adjust):
    prices = frame([100.0, np.nan, 110.0, 121.0, 145.2, np.nan])
    result = reversal(prices, window=2, skip=1, vol_adjust=vol_adjust)
    # 首尾有效不能掩盖窗口内部缺失；最后一行跳过的缺失价格不参与计算。
    assert result.iloc[:5].isna().all()
    expected = -np.log(145.2 / 110.0)
    if vol_adjust:
        expected /= np.std([np.log(1.1), np.log(1.2)], ddof=1)
    assert result.iloc[5] == pytest.approx(expected)


@pytest.mark.parametrize("vol_adjust", [False, True])
def test_flat_prices_zero_vol_and_insufficient_samples(vol_adjust):
    prices = frame([10.0] * 5)
    result = reversal(prices, window=2, vol_adjust=vol_adjust)
    assert result.iloc[:2].isna().all()
    if vol_adjust:
        assert result.isna().all()
    else:
        assert result.iloc[2:].eq(0).all()
    assert reversal(prices.iloc[:2], window=2, vol_adjust=vol_adjust).isna().all()


@pytest.mark.parametrize("vol_adjust", [False, True])
def test_multiple_tickers_irregular_records_sorting_and_input_preserved(vol_adjust):
    a = frame([1.0, 2.0, 8.0, 4.0, 16.0, 32.0, 8.0])
    b = frame([80.0, 40.0, 20.0, 30.0, 10.0, 15.0, 60.0], "B").iloc[::2]
    prices = pd.concat([a, b]).sample(frac=1, random_state=12)
    original = prices.copy(deep=True)
    kwargs = {"window": 2, "skip": 1, "vol_adjust": vol_adjust}
    result = reversal(prices, **kwargs)
    expected = pd.concat([reversal(a, **kwargs), reversal(b, **kwargs)]).sort_index()
    pd.testing.assert_series_equal(result, expected)
    pd.testing.assert_index_equal(result.index, prices.sort_index().index)
    assert result.xs("B", level="ticker").notna().any()
    pd.testing.assert_frame_equal(prices, original)


@pytest.mark.parametrize("vol_adjust", [False, True])
def test_empty_schema_and_custom_price_column(vol_adjust):
    prices = frame([1.0, 2.0, 8.0]).rename(columns={"adj_close": "close"})
    kwargs = {"window": 2, "vol_adjust": vol_adjust, "price_col": "close"}
    result = reversal(prices, **kwargs)
    expected = reversal(
        prices.rename(columns={"close": "adj_close"}),
        **{"window": 2, "vol_adjust": vol_adjust},
    )
    pd.testing.assert_series_equal(result, expected)
    empty = reversal(prices.iloc[:0], **kwargs)
    assert isinstance(empty, pd.Series) and empty.empty
    assert empty.name == result.name
    pd.testing.assert_index_equal(empty.index, prices.iloc[:0].index)
    with pytest.raises(ValueError, match="缺少必要列"):
        reversal(prices)


@pytest.mark.parametrize("parameter", ["window", "skip"])
@pytest.mark.parametrize("bad", [True, False, 1.5, "2", None])
def test_rejects_noninteger_periods(parameter, bad):
    with pytest.raises(TypeError, match=f"{parameter} 必须是整数"):
        reversal(frame([1.0]), **{parameter: bad})


@pytest.mark.parametrize("bad", [0, 1, "True", None])
def test_rejects_nonboolean_vol_adjust(bad):
    with pytest.raises(TypeError, match="vol_adjust 必须是布尔值"):
        reversal(frame([1.0]), vol_adjust=bad)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"window": 0}, "window 必须大于 0"),
        ({"window": -1}, "window 必须大于 0"),
        ({"skip": -1}, "skip 必须大于等于 0"),
        ({"window": 1}, "window 必须不小于 2"),
    ],
)
def test_rejects_out_of_range_periods(kwargs, match):
    with pytest.raises(ValueError, match=match):
        reversal(frame([1.0]), **kwargs)


def test_unadjusted_one_period_is_negative_log_return():
    prices = frame([1.0, 2.0, 8.0])
    result = reversal(prices, window=1, vol_adjust=False)
    np.testing.assert_allclose(result, [np.nan, -np.log(2), -np.log(4)], equal_nan=True)


def test_rejects_invalid_input_and_prices():
    prices = frame([1.0, 2.0, 8.0])
    with pytest.raises(TypeError, match="DataFrame"):
        reversal(prices["adj_close"])
    with pytest.raises(ValueError, match="to_date_ticker_frame"):
        reversal(prices.reset_index())
    with pytest.raises(ValueError, match="只有一条记录"):
        reversal(pd.concat([prices, prices.iloc[:1]]))
    missing = prices.reset_index()
    missing.loc[0, "ticker"] = None
    with pytest.raises(ValueError, match="不能包含缺失值"):
        reversal(missing.set_index(["date", "ticker"]))
    for bad in [0.0, -1.0]:
        with pytest.raises(ValueError, match="非缺失价格必须大于 0"):
            reversal(frame([1.0, bad]))


def test_public_exports_are_callable_functions():
    from quanttoolskit.factors.reversal import reversal as package_reversal
    from quanttoolskit.factors.reversal.base import reversal as base_reversal

    assert reversal is package_reversal is base_reversal
