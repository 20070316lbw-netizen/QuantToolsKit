"""动量因子公开接口。"""

from .base import cumulative_log_returns
from .base import momentum as _momentum
from .momentum import momentum_12_1

# 同名子模块导入后, 显式将包上的公开名称绑定回函数。
momentum = _momentum

__all__ = ["cumulative_log_returns", "momentum", "momentum_12_1"]
