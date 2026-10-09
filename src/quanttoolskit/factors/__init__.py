"""因子计算, 输入为 [date, ticker] DataFrame, 单因子返回同索引 Series。"""

from .momfactor import momentum, momentum_12_1

__all__ = ["momentum", "momentum_12_1"]
