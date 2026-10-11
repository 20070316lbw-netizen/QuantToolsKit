"""注册表调用、Series 拼接和本地数据库示范的回归测试。"""

import runpy
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from quanttoolskit.factors import momentum, momentum_12_1
from quanttoolskit.factors.engine import to_panel
from quanttoolskit.factors.momfactor import MOM_FACTORS


def _prices():
    index = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=254), ["A", "B"]],
        names=["date", "ticker"],
    )
    values = np.repeat(np.arange(254) / 100, 2)
    values[1::2] *= -1
    return pd.DataFrame({"adj_close": np.exp(values)}, index=index)


def test_registry_exports_and_keyword_call():
    from quanttoolskit.factors.momfactor import __all__ as exports
    from quanttoolskit.factors.momfactor.base import momentum as base_momentum

    assert momentum is base_momentum
    assert "momentum_12_1" in exports
    assert MOM_FACTORS["momentum_12_1"] is momentum_12_1
    result = MOM_FACTORS["momentum_12_1"](df=_prices())
    pd.testing.assert_series_equal(result, momentum_12_1(df=_prices()))
    np.testing.assert_allclose(result.dropna(), [2.31, -2.31, 2.31, -2.31])


@pytest.mark.parametrize("empty", [False, True])
def test_to_panel_preserves_series_missing_values_and_input(empty):
    factor = momentum_12_1(df=_prices()).iloc[::-1]
    if empty:
        factor = factor.iloc[:0]
    before = factor.copy(deep=True)
    result = to_panel(factor, "score")
    pd.testing.assert_series_equal(result, before.sort_index().rename("score"))
    pd.testing.assert_series_equal(factor, before)
    assert result.isna().sum() == factor.isna().sum()


def test_to_panel_rejects_invalid_type_index_and_duplicate_keys():
    factor = momentum_12_1(df=_prices())
    with pytest.raises(TypeError, match="Series"):
        to_panel(factor.to_frame(), "score")
    with pytest.raises(ValueError, match="MultiIndex"):
        to_panel(factor.reset_index(drop=True), "score")
    with pytest.raises(ValueError, match="只有一条记录"):
        to_panel(pd.concat([factor, factor.iloc[:1]]), "score")


@pytest.mark.parametrize("name", ["", " ", None, 1])
def test_to_panel_rejects_invalid_names(name):
    with pytest.raises((TypeError, ValueError), match="name"):
        to_panel(momentum_12_1(df=_prices()), name)


def test_self_contained_example_computes_and_standardizes(capsys):
    script = Path(__file__).resolve().parents[1] / "examples/momentum_12_1.py"
    namespace = runpy.run_path(str(script), run_name="__main__")
    result = namespace["factor_result"]
    assert result.name == "mom_12_1"
    assert result.isna().sum() == 24
    np.testing.assert_allclose(result.dropna(), [11 * np.log(2), -11 * np.log(2)])
    np.testing.assert_allclose(namespace["scores"].dropna(), [2**-0.5, -(2**-0.5)])
    assert "<function" not in capsys.readouterr().out


def test_engine_prints_computed_series_from_read_only_database(
    tmp_path, monkeypatch, capsys
):
    raw = _prices().reset_index()
    database = tmp_path / "prices.db"
    with duckdb.connect(str(database)) as connection:
        connection.register("raw", raw)
        connection.execute("CREATE TABLE prices AS SELECT * FROM raw")
    before = database.read_bytes()
    script = Path(__file__).resolve().parents[1] / "src/quanttoolskit/factors/engine.py"
    monkeypatch.setattr(sys, "argv", [str(script), "--db", str(database)])
    namespace = runpy.run_path(str(script), run_name="__main__")
    pd.testing.assert_series_equal(
        namespace["factor_result"], momentum_12_1(df=_prices())
    )
    output = capsys.readouterr().out
    assert "<function" not in output
    assert "mom_12_1" in output
    assert database.read_bytes() == before
