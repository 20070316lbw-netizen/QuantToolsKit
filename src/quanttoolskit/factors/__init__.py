"""因子计算，输入输出均为 [date, ticker] MultiIndex DataFrame。"""

from .momfactor import momentum, momentum_12_1

__all__ = ["momentum", "momentum_12_1"]
