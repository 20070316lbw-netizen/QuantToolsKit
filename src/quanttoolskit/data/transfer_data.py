"""对由数据库文件读出来的数据做必须的重复性处理

我们的数据由 DuckDB 存储, 读出来默认就是长表, 所以我们不要求使用者转成宽表
尽限本文件统一约定:
    - 输入为 prices 表; 价格列叫做 price_col, 默认等于 close
    - 计算前再次手动按股票和日期排序, 避免调用者随机组合项目内各种函数导致有些内容没有
        排序而出错
"""

from __future__ import annotations

import pandas as pd


def transfer_prices(
    *,
    df: pd.DataFrame,
    price_col: str,
) -> pd.Series:
    """将 prices 长表整理为按股票、日期排序的价格序列"""

    required = {"date", "ticker", price_col}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"缺少必要列: {sorted(missing)}")

    data = df.loc[:, ["date", "ticker", price_col]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise")

    if data[["date", "ticker"]].isna().any().any():
        raise ValueError("date 和 ticker 不能包含缺失值")

    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("每个 (date, ticker) 必须只有一条记录")

    data[price_col] = pd.to_numeric(data[price_col], errors="raise")
    if data[price_col].dropna().le(0).any():
        raise ValueError(f"{price_col} 中的非缺失价格必须大于 0")

    return data.sort_values(["ticker", "date"]).set_index(["date", "ticker"])[price_col]
