import numpy as np
import pandas as pd
import pytest

from quanttoolskit.data.transfer_data import to_date_ticker_frame, validate_prices


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


def test_converted_prices_are_sorted_by_date_then_ticker(prices_long):
    """按 (date, ticker) 排序, 返回保留全部列的数据框。"""
    result = validate_prices(df=to_date_ticker_frame(df=prices_long), price_col="close")

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == ["close", "volume"]
    assert result.index.names == ["date", "ticker"]
    assert result.index.is_unique
    assert result["close"].tolist() == [100.0, 50.0, 102.0, 51.0, 104.0]
    assert result.index.is_monotonic_increasing
    assert result["close"].dtype == np.float64


def test_validate_prices_keeps_all_data_columns(prices_long):
    """date/ticker 进入索引, 其他数据列全部保留。"""
    result = validate_prices(df=to_date_ticker_frame(df=prices_long), price_col="close")

    assert list(result.index.names) == ["date", "ticker"]
    assert list(result.columns) == ["close", "volume"]


def test_validate_prices_accepts_custom_price_col():
    """price_col 指向别的价格列时, 结果名跟着变。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-01"],
            "ticker": ["A", "A"],
            "adj_close": [2.0, 1.0],
        }
    )

    result = validate_prices(df=to_date_ticker_frame(df=df), price_col="adj_close")

    assert list(result.columns) == ["adj_close"]
    assert result["adj_close"].tolist() == [1.0, 2.0]


def test_validate_prices_does_not_mutate_input(prices_long):
    """不修改调用者传入的数据框。"""
    before = prices_long.copy(deep=True)

    validate_prices(df=to_date_ticker_frame(df=prices_long), price_col="close")

    pd.testing.assert_frame_equal(prices_long, before)


def test_validate_prices_rejects_missing_columns():
    """缺少 ticker 时给出明确的列名提示。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "close": [1.0]})

    with pytest.raises(ValueError) as excinfo:
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")

    message = str(excinfo.value)
    assert "缺少必要列" in message
    assert "ticker" in message
    assert "close" not in message


def test_validate_prices_rejects_missing_price_col():
    """price_col 不在列里时同样报缺少列。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "adj_close": [1.0]})

    with pytest.raises(ValueError, match="缺少必要列"):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


@pytest.mark.parametrize("bad_ticker", [None, np.nan])
def test_validate_prices_rejects_missing_ticker(bad_ticker):
    """ticker 缺失直接报错, 不做静默丢弃。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "ticker": ["A", bad_ticker],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="不能包含缺失值"):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


def test_validate_prices_rejects_missing_date():
    """date 缺失直接报错。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", None],
            "ticker": ["A", "A"],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="不能包含缺失值"):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


def test_validate_prices_rejects_duplicate_date_ticker():
    """同一个 (date, ticker) 出现两次说明上游去重没做好。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "ticker": ["A", "A"],
            "close": [1.0, 2.0],
        }
    )

    with pytest.raises(ValueError, match="必须只有一条记录"):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


@pytest.mark.parametrize("bad_price", [0.0, -1.0])
def test_validate_prices_rejects_non_positive_price(bad_price):
    """非缺失价格必须大于 0, 否则收益率的除数就没有意义。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": [bad_price]})

    with pytest.raises(ValueError, match="必须大于 0"):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


def test_validate_prices_allows_missing_price():
    """缺失价格保留为 NaN, 不报错也不填补。"""
    df = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "ticker": ["A", "A"],
            "close": [np.nan, 2.0],
        }
    )

    result = validate_prices(df=to_date_ticker_frame(df=df), price_col="close")

    assert np.isnan(result["close"].iloc[0])
    assert result["close"].iloc[1] == pytest.approx(2.0)


def test_validate_prices_coerces_numeric_strings():
    """数据库读出的数值列可能是字符串, 统一转成浮点。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": ["100.5"]})

    result = validate_prices(df=to_date_ticker_frame(df=df), price_col="close")

    assert result["close"].dtype == np.float64
    assert result["close"].iloc[0] == pytest.approx(100.5)


def test_validate_prices_rejects_unparsable_price():
    """价格无法转成数字时报错, 不静默变 NaN。"""
    df = pd.DataFrame({"date": ["2024-01-01"], "ticker": ["A"], "close": ["abc"]})

    with pytest.raises(ValueError):
        validate_prices(df=to_date_ticker_frame(df=df), price_col="close")


def test_validate_prices_handles_empty_frame():
    """空表返回空的 DataFrame, 而不是抛异常。"""
    df = pd.DataFrame(
        {
            "date": pd.Series(dtype="object"),
            "ticker": pd.Series(dtype="object"),
            "close": pd.Series(dtype="float64"),
        }
    )

    result = validate_prices(df=to_date_ticker_frame(df=df), price_col="close")

    assert result.empty
    assert result.index.names == ["date", "ticker"]


def test_transfer_data_is_idempotent_and_keeps_columns(prices_long):
    from quanttoolskit.data import to_date_ticker_frame

    before = prices_long.copy(deep=True)
    result = to_date_ticker_frame(df=prices_long)
    pd.testing.assert_frame_equal(to_date_ticker_frame(df=result), result)
    pd.testing.assert_frame_equal(prices_long, before)
    assert list(result.columns) == ["close", "volume"]
    assert isinstance(result.index.get_level_values("date"), pd.DatetimeIndex)


@pytest.mark.parametrize("names", [["ticker", "date"], ["day", "symbol"]])
def test_transfer_data_rejects_wrong_index_names(names):
    from quanttoolskit.data import to_date_ticker_frame

    frame = pd.DataFrame(
        {"close": [1.0]},
        index=pd.MultiIndex.from_tuples([("A", "2024-01-01")], names=names),
    )
    with pytest.raises(ValueError, match="索引必须"):
        to_date_ticker_frame(df=frame)


def test_validate_prices_detects_duplicates_after_date_conversion():
    frame = pd.DataFrame(
        {"date": ["2024-01-01", "2024-01-01"], "ticker": ["A", "A"], "close": [1, 2]}
    ).set_index(["date", "ticker"])
    with pytest.raises(ValueError, match="必须只有一条记录"):
        to_date_ticker_frame(df=frame)


def test_validate_prices_requires_converted_frame(prices_long):
    with pytest.raises(ValueError, match="to_date_ticker_frame"):
        validate_prices(df=prices_long)


def test_validate_prices_preserves_index_order_and_input(prices_long):
    frame = to_date_ticker_frame(df=prices_long).iloc[::-1].copy()
    frame["close"] = frame["close"].astype(str)
    before = frame.copy(deep=True)
    result = validate_prices(df=frame)
    assert result.index.equals(frame.index)
    assert pd.api.types.is_numeric_dtype(result["close"])
    pd.testing.assert_frame_equal(frame, before)


def test_validate_prices_rejects_string_date_index():
    frame = pd.DataFrame(
        {"date": ["2024-01-01"], "ticker": ["A"], "close": [1.0]}
    ).set_index(["date", "ticker"])
    with pytest.raises(ValueError, match="日期时间"):
        validate_prices(df=frame)
