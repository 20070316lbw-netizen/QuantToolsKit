"""动量因子公开接口, 调用示范见 docs/momentum.md。

MOM_FACTORS["momentum_12_1"] 返回函数, 使用 factor_fn(df=prices) 得到 Series。
"""

from collections.abc import Callable

import pandas as pd

from .base import cumulative_log_returns
from .base import momentum as _momentum
from .momentum import momentum_12_1

# 同名子模块导入后, 显式将包上的公开名称绑定回函数。
momentum = _momentum

MOM_FACTORS: dict[str, Callable[..., pd.Series]] = {
    "momentum_12_1": momentum_12_1,
}

__all__ = ["MOM_FACTORS", "cumulative_log_returns", "momentum", "momentum_12_1"]
