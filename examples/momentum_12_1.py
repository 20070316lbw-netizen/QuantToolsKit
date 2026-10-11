"""注册表调用经典 12-1 动量; 运行: uv run python examples/momentum_12_1.py。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data import to_date_ticker_frame
from quanttoolskit.factors.momfactor import MOM_FACTORS
from quanttoolskit.indicators import zscore_by_date

if __name__ == "__main__":
    dates = pd.bdate_range("2024-01-01", periods=13)
    raw = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "ticker": ["A"] * 13 + ["B"] * 13,
            "adj_close": [2.0**i for i in range(13)] + [2.0**-i for i in range(13)],
        }
    )
    prices = to_date_ticker_frame(df=raw)
    factor_fn = MOM_FACTORS["momentum_12_1"]
    # 为缩短自包含示范, 每月近似为 1 条记录; 实际默认值为 21。
    factor_result = factor_fn(df=prices, trading_days_per_month=1)
    print(factor_result)
    # 单因子已返回标准 Series, 直接 to_frame 后即可按日期标准化。
    scores = zscore_by_date(factor_result.to_frame())
    print(scores.dropna().round(6))
