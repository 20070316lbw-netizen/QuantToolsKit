"""标准分数的数值、日期隔离及输入契约测试。"""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from quanttoolskit.data.transfer_data import to_date_ticker_frame
from quanttoolskit.indicators import zscore_by_date


def factors():
    index = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=2), ["A", "B", "C"]],
        names=["date", "ticker"],
    )
    return pd.DataFrame(
        {"f1": [1, 2, 3, 100, 200, 300], "f2": [3, 2, 1, 3, 3, 3]}, index=index
    )


def test_each_date_and_column_are_independent_and_input_is_unchanged():
    data = factors().iloc[::-1]
    original = data.copy(deep=True)
    result = zscore_by_date(data)
    assert result.index.equals(data.sort_index().index)
    assert result.columns.equals(data.columns)
    assert result["f1"].tolist() == [-1, 0, 1, -1, 0, 1]
    assert result.iloc[:3]["f2"].tolist() == [1, 0, -1]
    assert result.iloc[3:]["f2"].isna().all()
    assert_frame_equal(data, original)
    assert np.allclose(result.groupby(level="date")["f1"].mean(), 0)
    assert np.allclose(result.groupby(level="date")["f1"].std(), 1)


def test_missing_singleton_and_constant_cross_sections():
    data = factors().assign(
        f1=[1, np.nan, 3, np.nan, 2, np.nan],
        constant=1,
        missing=np.nan,
    )
    result = zscore_by_date(data)
    assert result.iloc[0]["f1"] == pytest.approx(-1 / np.sqrt(2))
    assert result.iloc[2]["f1"] == pytest.approx(1 / np.sqrt(2))
    assert pd.isna(result.iloc[1]["f1"])
    assert result.iloc[3:]["f1"].isna().all()
    assert result[["constant", "missing"]].isna().all().all()


def test_empty_frame_and_numeric_strings():
    data = factors()
    empty = zscore_by_date(data.iloc[:0])
    assert empty.index.equals(data.iloc[:0].index)
    assert empty.columns.equals(data.columns)
    assert_frame_equal(zscore_by_date(data.astype(str)), zscore_by_date(data))
    no_columns = zscore_by_date(data.iloc[:, :0])
    assert no_columns.index.equals(data.index)


@pytest.mark.parametrize("bad", [np.inf, -np.inf, "not a number"])
def test_invalid_values(bad):
    data = factors().astype(object)
    data.iloc[0, 0] = bad
    with pytest.raises(ValueError):
        zscore_by_date(data)


def test_invalid_input_contract():
    data = factors()
    with pytest.raises(TypeError):
        zscore_by_date(data["f1"])
    with pytest.raises(ValueError):
        zscore_by_date(data.reset_index())
    with pytest.raises(ValueError):
        zscore_by_date(pd.concat([data, data]))
    with pytest.raises(ValueError):
        zscore_by_date(data, date_level="day")
    with pytest.raises(ValueError):
        zscore_by_date(data.swaplevel())
    with pytest.raises(ValueError):
        zscore_by_date(pd.concat([data, data], axis=1))
    missing_key = data.reset_index()
    missing_key.loc[0, "ticker"] = None
    with pytest.raises(ValueError):
        zscore_by_date(missing_key.set_index(["date", "ticker"]))
    non_datetime = data.reset_index().assign(date="2024-01-01")
    with pytest.raises(ValueError):
        zscore_by_date(non_datetime.set_index(["date", "ticker"]))


def test_irregular_dates_do_not_create_records():
    data = to_date_ticker_frame(
        df=pd.DataFrame(
            {"date": ["2024-01-01", "2024-01-03"], "ticker": ["A", "B"], "f1": [1, 2]}
        )
    )
    result = zscore_by_date(data)
    assert result.index.equals(data.index)
    assert result.isna().all().all()
