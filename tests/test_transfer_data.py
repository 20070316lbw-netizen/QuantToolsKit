import numpy as np
import pandas as pd
import pytest

from quanttoolskit.data.transfer_data import transfer_prices


@pytest.fixture
def prices_long():
    """两只股票、日期乱序、带额外列的长表行情。"""
    return pd.DataFrame(
        {
            "date": [
                "2024-01-02",
                "2024-01-01",
                "2024-01-03",
                "2024-01-01",
                "2024-01-02",
            ],
            "ticker": ["A", "A", "A", "B", "B"],
            "close": [102.0, 100.0, 104.0, 50.0, 51.0],
            "volume": [10.0, 11.0, 12.0, 13.0, 14.0],
        }
    )


def test_transfer_prices_sorts_by_ticker_then_date(prices_long):
    """先按股票、再按日期排序, 返回以 (date, ticker) 为索引的单列 Series。"""
    result = transfer_prices(df=prices_long, price_col="close")

    assert isinstance(result, pd.Series)
    assert result.name == "close"
    assert result.index.names == ["date", "ticker"]
    assert result.index.is_unique
    assert result.tolist() == [100.0, 102.0, 104.0, 50.0, 51.0]
    assert result.index.get_level_values("ticker").tolist() == [
        "A",
        "A",
        "A",
        "B",
        "B",
    ]
    assert [
        day.strftime("%Y-%m-%d") for day in result.index.get_level_values("date")
    ] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-01",
        "2024-01-02",
    ]
    assert result.dtype == np.float64


def test_transfer_prices_keeps_only_the_requested_columns(prices_long):
    """只保留 date/ticker/price_col, 其他列不进入返回结果。"""
    result = transfer_prices(df=prices_long, price_col="close")

    assert list(result.index.names) == ["date", "ticker"]
    assert result.name == "close"


def test_transfer_prices_accepts_custom_price_col():
    """price_col 指向别的价格列时, 结果名跟着变。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-01"],
            "ticker": ["A", "A"],
            "adj_close": [2.0, 1.0],
        }
    )

    result = transfer_prices(df=df, price_col="adj_close")

    assert result.name == "adj_close"
    assert result.tolist() == [1.0, 2.0]


def test_transfer_prices_does_not_mutate_input(prices_long):
    """不修改调用者传入的数据框。"""
    before = prices_long.copy(deep=True)

    transfer_prices(df=prices_long, price_col="close")

    pd.testing.assert_frame_equal(prices_long, before)


def test_transfer_prices_rejects_missing_columns():
    """缺少 ticker 时给出明确的列名提示。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "close": [1.0]})

    with pytest.raises(ValueError) as excinfo:
        transfer_prices(df=df, price_col="close")

    message = str(excinfo.value)
    assert "缺少必要列" in message
    assert "ticker" in message
    assert "close" not in message


def test_transfer_prices_rejects_missing_price_col():
    """price_col 不在列里时同样报缺少列。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "adj_close": [1.0]})

    with pytest.raises(ValueError, match="缺少必要列"):
        transfer_prices(df=df, price_col="close")


@pytest.mark.parametrize("bad_ticker", [None, np.nan])
def test_transfer_prices_rejects_missing_ticker(bad_ticker):
    """ticker 缺失直接报错, 不做静默丢弃。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "ticker": ["A", bad_ticker],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="不能包含缺失值"):
        transfer_prices(df=df, price_col="close")


def test_transfer_prices_rejects_missing_date():
    """date 缺失直接报错。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", None],
            "ticker": ["A", "A"],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="不能包含缺失值"):
        transfer_prices(df=df, price_col="close")


def test_transfer_prices_rejects_duplicate_date_ticker():
    """同一个 (date, ticker) 出现两次说明上游去重没做好。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "ticker": ["A", "A"],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="必须只有一条记录"):
        transfer_prices(df=df, price_col="close")


@pytest.mark.parametrize("bad_price", [0.0, -1.0])
def test_transfer_prices_rejects_non_positive_price(bad_price):
    """非缺失价格必须大于 0, 否则收益率的除数就没有意义。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": [bad_price]})

    with pytest.raises(ValueError, match="必须大于 0"):
        transfer_prices(df=df, price_col="close")


def test_transfer_prices_allows_missing_price():
    """缺失价格保留为 NaN, 不报错也不填补。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "ticker": ["A", "A"],
            "close": [np.nan, 2.0],
        }
    )

    result = transfer_prices(df=df, price_col="close")

    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == pytest.approx(2.0)


def test_transfer_prices_coerces_numeric_strings():
    """数据库读出的数值列可能是字符串, 统一转成浮点。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": ["100.5"]})

    result = transfer_prices(df=df, price_col="close")

    assert result.dtype == np.float64
    assert result.iloc[0] == pytest.approx(100.5)


def test_transfer_prices_rejects_unparsable_price():
    """价格无法转成数字时报错, 不静默变 NaN。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": ["abc"]})

    with pytest.raises(ValueError):
        transfer_prices(df=df, price_col="close")


def test_transfer_prices_handles_empty_frame():
    """空表返回空的 Series, 而不是抛异常。"""
    df = pd.DataFrame(
        {
            "date": pd.Series(dtype="object"),
            "ticker": pd.Series(dtype="object"),
            "close": pd.Series(dtype="float64"),
        }
    )

    result = transfer_prices(df=df, price_col="close")

    assert result.empty
    assert result.index.names == ["date", "ticker"]
