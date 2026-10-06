"""保证 AGENTS.md 引用的调用示范可执行且数值正确。"""

import runpy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

EXAMPLE = (
    Path(__file__).resolve().parents[1] / "examples" / "quantile_forward_returns.py"
)
namespace = runpy.run_path(str(EXAMPLE))
quantile_forward_returns = namespace["quantile_forward_returns"]
sample_data = namespace["sample_data"]


def test_example_values_and_no_input_mutation():
    scores, prices = sample_data()
    original_scores, original_prices = scores.copy(), prices.copy()
    result = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
    assert result.index.names == ["date", "ticker"]
    assert result.index.is_unique and result.index.is_monotonic_increasing
    assert result.columns.tolist() == ["forward_return"]
    assert result.iloc[0, 0] == 0
    assert result.iloc[1, 0] == pytest.approx(10 / 39)
    assert_frame_equal(scores, original_scores)
    assert_frame_equal(prices, original_prices)


def test_last_rebalance_has_no_exit_and_all_groups_are_retained():
    scores, prices = sample_data()
    date = prices.index.get_level_values("date").unique()[20]
    last = scores.copy()
    last.index = pd.MultiIndex.from_product(
        [[date], ["A", "B", "C", "D"]], names=["date", "ticker"]
    )
    result = quantile_forward_returns(
        pd.concat([scores, last]), prices, freq=20, n_quantiles=2
    )
    assert result.loc[date].isna().all().all()
    assert result.shape == (4, 1)
    empty_groups = quantile_forward_returns(
        scores.assign(score=1), prices, freq=20, n_quantiles=2
    )
    assert empty_groups.isna().all().all()


def test_missing_endpoints_uses_valid_members_without_filling():
    scores, prices = sample_data()
    dates = prices.index.get_level_values("date").unique()
    prices = prices.drop(index=(dates[20], "D"))
    prices.loc[(dates[20], "C"), "close"] = 1.2
    result = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
    assert result.iloc[1, 0] == pytest.approx(0.2)
    prices.loc[(dates[20], "C"), "close"] = np.nan
    result = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
    assert pd.isna(result.iloc[1, 0])


@pytest.mark.parametrize(
    "freq,error", [(True, TypeError), (1.5, TypeError), (0, ValueError)]
)
def test_invalid_frequency(freq, error):
    scores, prices = sample_data()
    with pytest.raises(error):
        quantile_forward_returns(scores, prices, freq=freq, n_quantiles=2)


def test_off_calendar_score_and_empty_scores():
    scores, prices = sample_data()
    with pytest.raises(ValueError, match="调仓日"):
        quantile_forward_returns(scores, prices.iloc[4:], freq=20, n_quantiles=2)
    empty = quantile_forward_returns(scores.iloc[:0], prices, freq=20, n_quantiles=2)
    assert empty.empty and empty.index.names == ["date", "ticker"]
    with pytest.raises(ValueError, match="有限"):
        quantile_forward_returns(
            scores, prices.assign(close=np.inf), freq=20, n_quantiles=2
        )


def test_agents_example_matches_executable_source():
    instructions = (EXAMPLE.parents[1] / "AGENTS.md").read_text()
    assert "```python\n" + EXAMPLE.read_text() + "```" in instructions


def test_zscore_then_quantile_returns_preserves_single_factor_ranking():
    standardize = namespace["zscore_by_date"]
    scores, prices = sample_data()
    raw = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
    standardized = standardize(scores)
    assert standardized.columns.tolist() == ["score"]
    assert standardized.index.equals(scores.index)
    assert_frame_equal(
        quantile_forward_returns(standardized, prices, freq=20, n_quantiles=2), raw
    )
    # 常数截面标准化后为 NaN, 无法分桶, 不生成虚构的有效收益。
    constant = standardize(scores.assign(score=1))
    result = quantile_forward_returns(constant, prices, freq=20, n_quantiles=2)
    assert result.isna().all().all()
