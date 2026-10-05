"""数据预处理工具。"""

import pandas as pd

from .transfer_data import to_date_ticker_frame


def set_datetime_index(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """兼容原函数名：现返回 (date, ticker) MultiIndex，必须提供 ticker。

    自定义日期列会改名为 date；新代码建议直接使用 to_date_ticker_frame。
    """
    if date_col != "date":
        if "date" in df.columns:
            raise ValueError("自定义日期列不能与已有 date 列冲突")
        df = df.rename(columns={date_col: "date"})
    return to_date_ticker_frame(df=df)
