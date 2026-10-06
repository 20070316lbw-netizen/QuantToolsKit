"""动量公式、缺失窗口、时序边界与输入契约的回归测试。"""

import numpy as np
import pandas as pd
import pytest

from quanttoolskit import log_returns
from quanttoolskit.factors import momentum, momentum_12_1


def _frame(values, ticker="A"):
    return pd.DataFrame(
        {"adj_close": values},
        index=pd.MultiIndex.from_arrays(
            [pd.date_range("2024-01-01", periods=len(values)), [ticker] * len(values)],
            names=["date", "ticker"],
        ),
    )


def test_log_returns_formula_default_price_and_input_preserved():
    df = _frame([100.0, 110.0, 99.0, np.nan, 120.0, 150.0])
    df["close"] = 1.0
    before = df.copy(deep=True)
    result = log_returns(df=df)
    expected = pd.DataFrame(
        {
            "log_return": [
                np.nan,
                np.log(1.1),
                np.log(0.9),
                np.nan,
                np.nan,
                np.log(1.25),
            ]
        },
        index=df.index,
    )
    pd.testing.assert_frame_equal(result, expected)
    pd.testing.assert_frame_equal(df, before)


@pytest.mark.parametrize("window,skip", [(1, 0), (2, 0), (2, 1), (3, 2)])
def test_momentum_matches_manual_price_ratios(window, skip):
    values = [100.0, 110.0, 99.0, 120.0, 90.0, 150.0, 125.0]
    df = _frame(values)
    result = momentum(df=df, window=window, skip=skip)
    expected = [
        np.nan
        if t < window + skip
        else np.log(values[t - skip] / values[t - skip - window])
        for t in range(len(values))
    ]
    assert result.columns.tolist() == [f"momentum_{window}_skip_{skip}"]
    pd.testing.assert_index_equal(result.index, df.index)
    np.testing.assert_allclose(result.iloc[:, 0], expected, atol=1e-14, equal_nan=True)


def test_momentum_requires_all_prices_in_window_and_recovers():
    df = _frame([100.0, np.nan, 110.0, 121.0, 133.1, 146.41])
    result = momentum(df=df, window=2, skip=1)
    # t=3 两个端点有价格, 但窗口中间价格缺失, 仍不能计算。
    assert result.iloc[:5, 0].isna().all()
    assert result.iloc[5, 0] == pytest.approx(np.log(133.1 / 110.0))


@pytest.mark.parametrize(
    "function",
    [log_returns, momentum_12_1, lambda **kw: momentum(window=2, skip=1, **kw)],
)
def test_group_isolation_sorting_gaps_and_input_preserved(function):
    a = _frame([100.0, 105.0, 95.0, 110.0, 130.0, 120.0] * 4)
    b = _frame([20.0, 30.0, 25.0, 50.0, 40.0, 60.0] * 4, "B").iloc[::2]
    b = pd.concat([b, _frame([1.0] * 24, "B").iloc[[-1]]])
    df = pd.concat([a, b]).sample(frac=1, random_state=42)
    before = df.copy(deep=True)
    kwargs = {"trading_days_per_month": 1} if function is momentum_12_1 else {}
    result = function(df=df, **kwargs)
    expected = pd.concat(
        [function(df=a, **kwargs), function(df=b, **kwargs)]
    ).sort_index()
    pd.testing.assert_frame_equal(result, expected)
    assert result.xs("A", level="ticker").notna().any().iloc[0]
    assert result.xs("B", level="ticker").notna().any().iloc[0]
    pd.testing.assert_index_equal(result.index, df.sort_index().index)
    pd.testing.assert_frame_equal(df, before)


@pytest.mark.parametrize("m", [1, 2, 21])
def test_12_1_uses_eleven_month_window_and_skips_one_month(m):
    values = np.exp(np.arange(12 * m + 2) / 100)
    df = _frame(values)
    result = momentum_12_1(df=df, trading_days_per_month=m)
    assert result.columns.tolist() == ["mom_12_1"]
    assert result.iloc[: 12 * m, 0].isna().all()
    assert result.iloc[12 * m, 0] == pytest.approx(11 * m / 100)
    changed = df.copy()
    changed.iloc[-m:, 0] *= 10
    pd.testing.assert_frame_equal(
        result, momentum_12_1(df=changed, trading_days_per_month=m)
    )


def test_default_12_1_matches_explicit_twenty_one_days():
    df = _frame(np.exp(np.arange(255) / 100))
    pd.testing.assert_frame_equal(
        momentum_12_1(df=df), momentum_12_1(df=df, trading_days_per_month=21)
    )


@pytest.mark.parametrize("parameter", ["window", "skip", "trading_days_per_month"])
@pytest.mark.parametrize("bad", [True, False, 1.5, "2", None])
def test_rejects_non_integer_parameters(parameter, bad):
    kwargs = {parameter: bad}
    with pytest.raises(TypeError, match=f"{parameter} 必须是整数"):
        if parameter == "trading_days_per_month":
            momentum_12_1(df=_frame([1.0]), **kwargs)
        else:
            momentum(df=_frame([1.0]), **({"window": 2} | kwargs))


@pytest.mark.parametrize(
    "parameter,bad",
    [
        ("window", 0),
        ("window", -1),
        ("skip", -1),
        ("trading_days_per_month", 0),
        ("trading_days_per_month", -1),
    ],
)
def test_rejects_out_of_range_parameters(parameter, bad):
    with pytest.raises(ValueError, match=parameter):
        if parameter == "trading_days_per_month":
            momentum_12_1(df=_frame([1.0]), **{parameter: bad})
        else:
            momentum(df=_frame([1.0]), **({"window": 2} | {parameter: bad}))


@pytest.mark.parametrize(
    "function", [log_returns, momentum_12_1, lambda **kw: momentum(window=2, **kw)]
)
def test_empty_frame_and_custom_price_column(function):
    df = _frame([]).rename(columns={"adj_close": "price"})
    result = function(df=df, price_col="price")
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (0, 1)
    pd.testing.assert_index_equal(result.index, df.index)
    df = _frame([1.0, 2.0, 4.0]).rename(columns={"adj_close": "price"})
    assert function(df=df, price_col="price").shape == (3, 1)
    with pytest.raises(ValueError, match="缺少必要列"):
        function(df=df)


@pytest.mark.parametrize("bad", [0.0, -1.0])
@pytest.mark.parametrize(
    "function", [log_returns, momentum_12_1, lambda **kw: momentum(window=2, **kw)]
)
def test_rejects_non_positive_prices(function, bad):
    with pytest.raises(ValueError, match="非缺失价格必须大于 0"):
        function(df=_frame([1.0, bad]))


@pytest.mark.parametrize(
    "function", [log_returns, momentum_12_1, lambda **kw: momentum(window=2, **kw)]
)
def test_rejects_invalid_keys_and_unconverted_input(function):
    df = _frame([1.0, 2.0])
    with pytest.raises(ValueError, match="只有一条记录"):
        function(df=pd.concat([df, df.iloc[:1]]))
    with pytest.raises(ValueError, match="to_date_ticker_frame"):
        function(df=df.reset_index())
    missing = df.reset_index()
    missing.loc[0, "ticker"] = None
    with pytest.raises(ValueError, match="不能包含缺失值"):
        function(df=missing.set_index(["date", "ticker"]))


def test_log_returns_avoids_overflow_in_price_ratio():
    result = log_returns(df=_frame([1e-300, 1e300]))
    assert result.iloc[1, 0] == pytest.approx(600 * np.log(10))


def test_momentum_package_exports_are_functions():
    from quanttoolskit.factors.momfactor import momentum as package_momentum
    from quanttoolskit.factors.momfactor.base import momentum as base_momentum

    assert momentum is package_momentum is base_momentum
