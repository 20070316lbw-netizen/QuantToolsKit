"""验证累计收益到反转、标准化、分桶的可运行示范。"""

import runpy
from pathlib import Path

import numpy as np
import pandas as pd


def test_example_executes_and_preserves_reversal_ranking(capsys):
    path = Path(__file__).resolve().parents[1] / "examples" / "return_factors.py"
    namespace = runpy.run_path(str(path), run_name="__main__")
    prices = namespace["prices"]
    cumulative = namespace["cumulative"]
    raw = namespace["raw_reversal"]
    adjusted = namespace["adjusted_reversal"]
    pd.testing.assert_series_equal(raw, (-cumulative).rename(raw.name))
    date = pd.Timestamp("2024-01-03")
    np.testing.assert_allclose(cumulative.loc[date], [np.log(8), -np.log(8)])
    np.testing.assert_allclose(adjusted.loc[date], [-3 * np.sqrt(2), 3 * np.sqrt(2)])
    buckets = namespace["buckets"]
    pd.testing.assert_index_equal(buckets.index, prices.index)
    assert buckets.name == "bucket"
    assert buckets.loc[:"2024-01-02"].isna().all()
    assert buckets.loc[date].tolist() == [0.0, 1.0]
    assert "cumulative_log_return_2_skip_0" in capsys.readouterr().out
