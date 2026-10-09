"""执行调仓日历与净值示范, 对照固定持仓的价格估值。"""

import runpy
from pathlib import Path

import pandas as pd

from quanttoolskit.performance import buy_and_hold_nav


def test_example_uses_common_calendar_and_matches_buy_and_hold(capsys):
    path = Path(__file__).resolve().parents[1] / "examples" / "rebalance_nav.py"
    namespace = runpy.run_path(str(path), run_name="__main__")
    prices = namespace["prices"]
    calendar = namespace["calendar"]
    assert len(calendar) == 7
    assert len(prices.xs("B", level="ticker")) == 5
    assert namespace["selected"].strftime("%Y-%m-%d").tolist() == [
        "2024-01-01",
        "2024-01-04",
        "2024-01-09",
    ]
    assert namespace["belong"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-01",
        "2024-01-01",
        "2024-01-01",
        "2024-01-04",
        "2024-01-04",
        "2024-01-04",
        "2024-01-09",
    ]
    single_holding = prices.xs("A", level="ticker", drop_level=False)
    pd.testing.assert_series_equal(
        namespace["nav"], buy_and_hold_nav(single_holding, initial_capital=100.0)
    )
    assert "rebalance_date" in capsys.readouterr().out
