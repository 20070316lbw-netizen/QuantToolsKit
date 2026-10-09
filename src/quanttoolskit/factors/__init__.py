"""因子计算, 输入为 [date, ticker] DataFrame, 单因子返回同索引 Series。"""

from .momfactor import cumulative_log_returns, momentum, momentum_12_1
from .reversal import reversal

__all__ = ["cumulative_log_returns", "momentum", "momentum_12_1", "reversal"]
