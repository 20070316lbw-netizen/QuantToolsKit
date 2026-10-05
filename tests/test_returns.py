import numpy as np
import pandas as pd
import pytest

from quanttoolskit.returns import future_returns, historical_return

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


def test_future_returns_matches_manual_formula():
    """label[t] = price[t + gap + n] / price[t + gap] - 1, 尾部记录不足为 NaN。"""
    result = future_returns(df=_frame(), n_periods=2, gap=1)

    expected = [
        PRICES[3] / PRICES[1] - 1,
        PRICES[4] / PRICES[2] - 1,
        PRICES[5] / PRICES[3] - 1,
        np.nan,
        np.nan,
        np.nan,
    ]

    assert result.columns[0] == "forward_return_2_gap_1"
    assert result.index.names == ["date", "ticker"]
    np.testing.assert_allclose(
        result.iloc[:, 0].to_numpy(), expected, rtol=1e-12, atol=0.0, equal_nan=True
    )


def test_future_returns_gap_zero_starts_today():
    """gap=0 时用当天收盘价入场。"""
    result = future_returns(df=_frame(), n_periods=2, gap=0)

    assert result.iloc[0, 0] == pytest.approx(PRICES[2] / PRICES[0] - 1)
    assert result.iloc[3, 0] == pytest.approx(PRICES[5] / PRICES[3] - 1)
    assert np.isnan(result.iloc[4, 0])
    assert np.isnan(result.iloc[5, 0])


def test_future_returns_index_is_sorted():
    """输出固定按 (date, ticker) 排序, 与入参顺序无关。"""
    shuffled = _frame().sample(frac=1.0, random_state=7)

    result = future_returns(df=shuffled, n_periods=2, gap=1)

    assert result.index.is_monotonic_increasing
    assert result.index.equals(result.sort_index().index)


def test_future_returns_unsorted_input_matches_sorted_input():
    """乱序输入与有序输入得到同一结果。"""
    sorted_df = _frame()
    shuffled = sorted_df.sample(frac=1.0, random_state=42)

    pd.testing.assert_frame_equal(
        future_returns(df=shuffled, n_periods=2, gap=1),
        future_returns(df=sorted_df, n_periods=2, gap=1),
    )


def test_future_returns_does_not_leak_across_tickers():
    """每只股票按自己的交易日序列 shift, 不跨股票取值。"""
    first = _frame(ticker="A")
    second = _frame(prices=OTHER_PRICES, ticker="B")
    combined = pd.concat([first, second])

    result = future_returns(df=combined, n_periods=2, gap=1)

    assert result.index.is_unique
    assert len(result) == len(PRICES) * 2
    assert result.loc[(DATES[0], "A")].iloc[0] == pytest.approx(
        PRICES[3] / PRICES[1] - 1
    )
    assert result.loc[(DATES[0], "B")].iloc[0] == pytest.approx(
        OTHER_PRICES[3] / OTHER_PRICES[1] - 1
    )
    per_ticker = pd.concat(
        [
            future_returns(df=first, n_periods=2, gap=1),
            future_returns(df=second, n_periods=2, gap=1),
        ]
    ).sort_index()
    pd.testing.assert_frame_equal(result, per_ticker)


def test_future_returns_uses_requested_price_col():
    """price_col 可以指向 adj_close。"""
    df = _frame().rename(columns={"close": "adj_close"})

    result = future_returns(df=df, n_periods=2, gap=1, price_col="adj_close")

    assert result.iloc[0, 0] == pytest.approx(PRICES[3] / PRICES[1] - 1)


def test_future_returns_rejects_frame_without_price_col():
    """缺少价格列时透传预处理层的报错。"""
    df = _frame().rename(columns={"close": "adj_close"})

    with pytest.raises(ValueError, match="缺少必要列"):
        future_returns(df=df)


@pytest.mark.parametrize("bad", [0, -1, -5])
def test_future_returns_rejects_non_positive_n_periods(bad):
    with pytest.raises(ValueError, match="n_periods 必须大于 0"):
        future_returns(df=_frame(), n_periods=bad)


@pytest.mark.parametrize("bad", [1.5, "2", True, None])
def test_future_returns_rejects_non_integer_n_periods(bad):
    with pytest.raises(TypeError, match="n_periods 必须是整数"):
        future_returns(df=_frame(), n_periods=bad)


@pytest.mark.parametrize("bad", [-1, -5])
def test_future_returns_rejects_negative_gap(bad):
    with pytest.raises(ValueError, match="gap 必须大于等于 0"):
        future_returns(df=_frame(), gap=bad)


@pytest.mark.parametrize("bad", [1.0, "1", True, None])
def test_future_returns_rejects_non_integer_gap(bad):
    with pytest.raises(TypeError, match="gap 必须是整数"):
        future_returns(df=_frame(), gap=bad)


def test_future_returns_defaults_are_five_periods_one_gap():
    """默认参数是 gap=1、n_periods=5, 名字体现出来。"""
    result = future_returns(df=_frame())

    assert result.columns[0] == "forward_return_5_gap_1"


def test_historical_return_matches_manual_formula():
    """return[t] = price[t] / price[t - n] - 1, 起始记录不足为 NaN。"""
    result = historical_return(df=_frame(), n_periods=2)

    expected = [
        np.nan,
        np.nan,
        PRICES[2] / PRICES[0] - 1,
        PRICES[3] / PRICES[1] - 1,
        PRICES[4] / PRICES[2] - 1,
        PRICES[5] / PRICES[3] - 1,
    ]

    assert result.columns[0] == "historical_return_2"
    assert result.index.names == ["date", "ticker"]
    np.testing.assert_allclose(
        result.iloc[:, 0].to_numpy(), expected, rtol=1e-12, atol=0.0, equal_nan=True
    )


def test_historical_return_does_not_leak_across_tickers():
    """历史收益率同样按股票分组回看。"""
    first = _frame(ticker="A")
    second = _frame(prices=OTHER_PRICES, ticker="B")
    combined = pd.concat([first, second])

    result = historical_return(df=combined, n_periods=2)

    assert result.loc[(DATES[2], "A")].iloc[0] == pytest.approx(
        PRICES[2] / PRICES[0] - 1
    )
    assert result.loc[(DATES[2], "B")].iloc[0] == pytest.approx(
        OTHER_PRICES[2] / OTHER_PRICES[0] - 1
    )


def test_historical_return_uses_requested_price_col():
    df = _frame().rename(columns={"close": "adj_close"})

    result = historical_return(df=df, n_periods=2, price_col="adj_close")

    assert result.iloc[2, 0] == pytest.approx(PRICES[2] / PRICES[0] - 1)


def test_historical_return_unsorted_input_matches_sorted_input():
    sorted_df = _frame()
    shuffled = sorted_df.sample(frac=1.0, random_state=3)

    pd.testing.assert_frame_equal(
        historical_return(df=shuffled, n_periods=2),
        historical_return(df=sorted_df, n_periods=2),
    )


@pytest.mark.parametrize("bad", [0, -2])
def test_historical_return_rejects_non_positive_n_periods(bad):
    with pytest.raises(ValueError, match="n_periods 必须大于 0"):
        historical_return(df=_frame(), n_periods=bad)


@pytest.mark.parametrize("bad", [2.0, "2", True])
def test_historical_return_rejects_non_integer_n_periods(bad):
    with pytest.raises(TypeError, match="n_periods 必须是整数"):
        historical_return(df=_frame(), n_periods=bad)
