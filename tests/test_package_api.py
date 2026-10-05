"""包根 __init__ 暴露的公开接口。"""

import quanttoolskit
from quanttoolskit import (
    forward_volatility,
    future_returns,
    historical_return,
    history_vol,
)
from quanttoolskit.returns import future_returns as future_returns_module
from quanttoolskit.returns import historical_return as historical_return_module
from quanttoolskit.volatility import forward_volatility as forward_volatility_module
from quanttoolskit.volatility import history_vol as history_vol_module


def test_package_root_exports_the_same_objects_as_the_modules():
    """从包根导入的四个函数就是模块里定义的那一个对象。"""
    assert future_returns is future_returns_module
    assert historical_return is historical_return_module
    assert history_vol is history_vol_module
    assert forward_volatility is forward_volatility_module


def test_all_covers_the_four_functions():
    """四个函数都登记进 __all__, 支持 from quanttoolskit import *。"""
    assert {
        "forward_volatility",
        "future_returns",
        "historical_return",
        "history_vol",
    } <= set(quanttoolskit.__all__)


def test_every_exported_name_resolves():
    """__all__ 里的名字都能在包上取到, 避免文档与导出脱节。"""
    for name in quanttoolskit.__all__:
        assert callable(getattr(quanttoolskit, name))


def test_functions_are_usable_through_the_package_root():
    """包根导入的入口可以真正跑出结果。"""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=8),
            "ticker": "A",
            "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
        }
    )

    frame = frame.set_index(["date", "ticker"])

    # 8 条记录: 未来收益要 t+3 有价 -> 5 个; 历史收益回看 2 期 -> 6 个;
    # 波动率窗口 3 -> 5 个; 未来波动要 t+4 有滚动值 -> 4 个。
    assert future_returns(df=frame, n_periods=2, gap=1).notna().sum().iloc[0] == 5
    assert historical_return(df=frame, n_periods=2).notna().sum().iloc[0] == 6
    assert history_vol(df=frame, window=3).notna().sum().iloc[0] == 5
    assert forward_volatility(df=frame, window=3, gap=1).notna().sum().iloc[0] == 4
