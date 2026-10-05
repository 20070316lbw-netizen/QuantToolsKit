import pandas as pd
import pytest

from quanttoolskit.data.preprocessing import set_datetime_index


def test_set_datetime_index_sucess():
    """测试正常的日期转换和排序"""

    # 1. 准备打乱顺序的假数据
    fake_df = pd.DataFrame(
        {
            "date": ["2023-01-03", "2023-01-01", "2023-01-02"],
            "adj_close": [150.0, 100.0, 120.0],
        }
    )

    result_df = set_datetime_index(fake_df, date_col="date")
    assert fake_df["date"].tolist() == ["2023-01-03", "2023-01-01", "2023-01-02"]
    assert isinstance(fake_df.index, pd.RangeIndex)

    assert isinstance(result_df.index, pd.DatetimeIndex)
    assert len(result_df) == 3
    assert result_df.index[0].strftime("%Y-%m-%d") == "2023-01-01"
    assert result_df.loc["2023-01-02", "adj_close"] == 120


def test_set_datetime_index_missing_column():
    """测试传入错误的列名时，是否抛出预期的异常"""
    fake_df = pd.DataFrame({"wrong_col": ["2023-01-01"]})

    with pytest.raises(ValueError):
        set_datetime_index(fake_df, date_col="date")
