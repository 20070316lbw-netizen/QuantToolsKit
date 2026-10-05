import numpy as np
import pandas as pd
import pytest

from quanttoolskit.volatility import forward_volatility, history_vol

DATES = pd.to_datetime(
    [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-04",
        "2024-01-05",
        "2024-01-08",
    ]
)
PRICES = [100.0, 105.0, 99.0, 108.0, 95.0, 112.0]
OTHER_PRICES = [50.0, 51.0, 52.0, 49.0, 55.0, 54.0]


def _frame(prices=None, ticker="A"):
    return pd.DataFrame(
        {
            "date": DATES,
            "ticker": ticker,
            "close": list(PRICES if prices is None else prices),
        }
    ).set_index(["date", "ticker"])


def _daily_returns(prices):
    """用 numpy 独立算一遍日简单收益率, 作为期望值的来源。"""
    prices = np.asarray(prices, dtype=float)
    return np.concatenate([[np.nan], prices[1:] / prices[:-1] - 1])


def test_history_vol_matches_manual_rolling_sample_std():
    """波动率 = 最近 window 个日收益率的样本标准差 (ddof=1)。"""
    window = 3

    result = history_vol(df=_frame(), window=window)

    returns = _daily_returns(PRICES)
    expected = [
        np.nan if i < window else np.std(returns[i - window + 1 : i + 1], ddof=1)
        for i in range(len(PRICES))
    ]

    assert result.columns[0] == "volatility_3"
    assert result.index.names == ["date", "ticker"]
    np.testing.assert_allclose(
        result.iloc[:, 0].to_numpy(), expected, rtol=1e-12, atol=0.0, equal_nan=True
    )


def test_history_vol_needs_window_plus_one_records():
    """需要 window + 1 条价格才能首次给出非 NaN。"""
    result = history_vol(df=_frame(), window=3)

    assert result.iloc[:3].isna().all().all()
    assert result.iloc[3:].notna().all().all()


def test_history_vol_constant_return_is_zero():
    """价格按固定比例复利时, 日收益率恒定, 样本标准差为 0。"""
    prices = [100.0 * 1.1**i for i in range(6)]

    result = history_vol(df=_frame(prices=prices), window=3)

    assert result.iloc[3:].abs().to_numpy().max() == pytest.approx(0.0, abs=1e-12)


def test_history_vol_propagates_missing_price():
    """价格缺失不填补: 任何包含缺失收益率的窗口都是 NaN。"""
    prices = [100.0, 105.0, np.nan, 108.0, 95.0, 112.0]

    result = history_vol(df=_frame(prices=prices), window=2)

    assert result.iloc[:5].isna().all().all()
    assert result.iloc[5, 0] == pytest.approx(
        np.std([95.0 / 108.0 - 1, 112.0 / 95.0 - 1], ddof=1)
    )


def test_history_vol_does_not_leak_across_tickers():
    """每只股票独立滚动, 不跨股票取值。"""
    first = _frame(ticker="A")
    second = _frame(prices=OTHER_PRICES, ticker="B")
    combined = pd.concat([first, second])

    result = history_vol(df=combined, window=3)

    assert result.index.is_unique
    assert len(result) == len(PRICES) * 2
    returns_b = _daily_returns(OTHER_PRICES)
    assert result.loc[(DATES[3], "A")].iloc[0] == pytest.approx(
        np.std(_daily_returns(PRICES)[1:4], ddof=1)
    )
    assert result.loc[(DATES[3], "B")].iloc[0] == pytest.approx(
        np.std(returns_b[1:4], ddof=1)
    )
    per_ticker = pd.concat(
        [
            history_vol(df=first, window=3),
            history_vol(df=second, window=3),
        ]
    ).sort_index()
    pd.testing.assert_frame_equal(result, per_ticker)


def test_history_vol_uses_requested_price_col():
    df = _frame().rename(columns={"close": "adj_close"})

    result = history_vol(df=df, window=3, price_col="adj_close")

    assert result.columns[0] == "volatility_3"
    assert result.iloc[3, 0] == pytest.approx(
        np.std(_daily_returns(PRICES)[1:4], ddof=1)
    )


@pytest.mark.parametrize("bad", [0, 1, -3])
def test_history_vol_rejects_small_window(bad):
    with pytest.raises(ValueError, match="window 必须大于等于 2"):
        history_vol(df=_frame(), window=bad)


@pytest.mark.parametrize("bad", [2.0, "3", True, None])
def test_history_vol_rejects_non_integer_window(bad):
    with pytest.raises(TypeError, match="window 必须是整数"):
        history_vol(df=_frame(), window=bad)


def test_forward_volatility_matches_manual_formula():
    """vol[t] = std(r[t + gap + 1], ..., r[t + gap + window]), ddof=1。"""
    window, gap = 3, 1

    result = forward_volatility(df=_frame(), window=window, gap=gap)

    returns = _daily_returns(PRICES)
    expected = []
    for i in range(len(PRICES)):
        start = i + gap + 1
        stop = i + gap + window + 1
        expected.append(
            np.std(returns[start:stop], ddof=1) if stop <= len(PRICES) else np.nan
        )

    assert result.columns[0] == "forward_volatility_3_gap_1"
    assert result.index.names == ["date", "ticker"]
    np.testing.assert_allclose(
        result.iloc[:, 0].to_numpy(), expected, rtol=1e-12, atol=0.0, equal_nan=True
    )


def test_forward_volatility_gap_zero():
    """gap=0 从下一个收益率开始取窗口。"""
    window, gap = 2, 0

    result = forward_volatility(df=_frame(), window=window, gap=gap)

    returns = _daily_returns(PRICES)
    assert result.iloc[0, 0] == pytest.approx(np.std(returns[1:3], ddof=1))
    assert result.iloc[3, 0] == pytest.approx(np.std(returns[4:6], ddof=1))
    assert np.isnan(result.iloc[4, 0])
    assert np.isnan(result.iloc[5, 0])


def test_forward_volatility_does_not_leak_across_tickers():
    """未来窗口也只在同一只股票内滑动。"""
    first = _frame(ticker="A")
    second = _frame(prices=OTHER_PRICES, ticker="B")
    combined = pd.concat([first, second])

    result = forward_volatility(df=combined, window=3, gap=1)

    assert result.index.is_unique
    assert len(result) == len(PRICES) * 2
    returns_a = _daily_returns(PRICES)
    returns_b = _daily_returns(OTHER_PRICES)
    assert result.loc[(DATES[0], "A")].iloc[0] == pytest.approx(
        np.std(returns_a[2:5], ddof=1)
    )
    assert result.loc[(DATES[0], "B")].iloc[0] == pytest.approx(
        np.std(returns_b[2:5], ddof=1)
    )
    per_ticker = pd.concat(
        [
            forward_volatility(df=first, window=3, gap=1),
            forward_volatility(df=second, window=3, gap=1),
        ]
    ).sort_index()
    pd.testing.assert_frame_equal(result, per_ticker)


def test_forward_volatility_uses_requested_price_col():
    df = _frame().rename(columns={"close": "adj_close"})

    result = forward_volatility(df=df, window=3, gap=1, price_col="adj_close")

    assert result.iloc[0, 0] == pytest.approx(
        np.std(_daily_returns(PRICES)[2:5], ddof=1)
    )


def test_forward_volatility_propagates_missing_price():
    """窗口里有缺失收益率时结果为 NaN, 不做填补。"""
    prices = [100.0, 105.0, np.nan, 108.0, 95.0, 112.0]

    result = forward_volatility(df=_frame(prices=prices), window=2, gap=0)

    # 缺失价格污染了 r[2]、r[3], 只有完全落在有效区间上的 t=3 有值
    assert result.iloc[:3].isna().all().all()
    assert result.iloc[3, 0] == pytest.approx(
        np.std([95.0 / 108.0 - 1, 112.0 / 95.0 - 1], ddof=1)
    )


@pytest.mark.parametrize("bad", [0, 1])
def test_forward_volatility_rejects_small_window(bad):
    with pytest.raises(ValueError, match="window 必须大于等于 2"):
        forward_volatility(df=_frame(), window=bad)


@pytest.mark.parametrize("bad", [2.0, True, "3"])
def test_forward_volatility_rejects_non_integer_window(bad):
    with pytest.raises(TypeError, match="window 必须是整数"):
        forward_volatility(df=_frame(), window=bad)


@pytest.mark.parametrize("bad", [-1, -2])
def test_forward_volatility_rejects_negative_gap(bad):
    with pytest.raises(ValueError, match="gap 必须大于等于 0"):
        forward_volatility(df=_frame(), gap=bad)


@pytest.mark.parametrize("bad", [1.0, True, "1"])
def test_forward_volatility_rejects_non_integer_gap(bad):
    with pytest.raises(TypeError, match="gap 必须是整数"):
        forward_volatility(df=_frame(), gap=bad)
