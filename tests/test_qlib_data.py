"""Qlib 来源边界、事务替换和手写 SQL 往返验证。"""

import builtins
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import duckdb
import numpy as np
import pandas as pd
import pytest

from quanttoolskit.data import (
    read_qlib_prices,
    save_qlib_prices,
    to_date_ticker_frame,
    writer,
)

HAS_QLIB = importlib.util.find_spec("qlib") is not None


@pytest.fixture
def provider(tmp_path):
    root = tmp_path / "cn_data"
    (root / "calendars").mkdir(parents=True)
    (root / "calendars/day.txt").write_text("2024-01-02\n2024-01-03\n2024-01-04\n")
    (root / "instruments").mkdir()
    (root / "instruments/all.txt").write_text(
        "SH600000\t2024-01-02\t2024-01-04\nSZ000001\t2024-01-02\t2024-01-04\n"
    )
    (root / "instruments/csi300.txt").write_text(
        "SH600000\t2024-01-02\t2024-01-02\nSZ000001\t2024-01-03\t2024-01-04\n"
    )
    fields = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "factor",
        "adjclose",
        "amount",
        "change",
        "vwap",
        "extra_metric",
    ]
    for ticker, multiplier in [("sh600000", 1), ("sz000001", 2)]:
        folder = root / "features" / ticker
        folder.mkdir(parents=True)
        for field in fields:
            if field == "extra_metric" and ticker == "sz000001":
                continue
            values = [0, multiplier, np.nan, multiplier * 3]
            np.array(values, dtype="<f4").tofile(folder / f"{field}.day.bin")
    return root


@pytest.fixture
def qlib_stub(monkeypatch):
    calls = {}
    index = pd.MultiIndex.from_tuples(
        [
            ("SZ000001", pd.Timestamp("2024-01-04")),
            ("SH600000", pd.Timestamp("2024-01-02")),
            ("SH600000", pd.Timestamp("2024-01-03")),
        ],
        names=["instrument", "datetime"],
    )

    def features(**kwargs):
        calls.update(kwargs)
        return pd.DataFrame(
            {
                field: np.array([3, 1, np.nan], dtype="float32")
                for field in kwargs["fields"]
            },
            index=index,
        )

    api = SimpleNamespace(
        features=features, instruments=lambda market: {"market": market}
    )
    monkeypatch.setitem(
        sys.modules, "qlib", SimpleNamespace(init=lambda **kw: calls.update(init=kw))
    )
    monkeypatch.setitem(sys.modules, "qlib.constant", SimpleNamespace(REG_CN="cn"))
    monkeypatch.setitem(sys.modules, "qlib.data", SimpleNamespace(D=api))
    return calls, api


def test_read_preserves_all_source_fields_values_and_standard_index(
    provider, qlib_stub
):
    result = read_qlib_prices(
        data_dir=provider,
        start="2024-01-02",
        end="2024-01-04",
        tickers=["sh600000", "SZ000001"],
    )
    calls, _ = qlib_stub
    assert calls["instruments"] == ["SH600000", "SZ000001"]
    assert calls["freq"] == "day" and calls["disk_cache"] == 0
    assert calls["init"]["kernels"] == 1
    assert result.index.names == ["date", "ticker"]
    assert result.index.is_unique and result.index.is_monotonic_increasing
    assert {"adjclose", "amount", "change", "vwap", "extra_metric"} <= set(result)
    assert "adj_close" not in result
    assert all(dtype == np.dtype("float32") for dtype in result.dtypes)
    assert result["close"].iloc[0] == 1
    assert pd.isna(result["close"].iloc[1])
    assert result["close"].iloc[2] == 3
    assert len(result) == 3  # 不因为缺价而删除, 也不补齐 date/ticker 网格。


def test_market_selection_is_passed_to_qlib(provider, qlib_stub):
    read_qlib_prices(
        data_dir=provider, start="2024-01-02", end="2024-01-04", market="csi300"
    )
    assert qlib_stub[0]["instruments"] == {"market": "csi300"}


def test_empty_result_has_datetime_multiindex_and_source_columns(provider, qlib_stub):
    _, api = qlib_stub

    def empty(**kw):
        return pd.DataFrame(
            index=pd.MultiIndex.from_arrays([[], []], names=["instrument", "datetime"]),
            columns=kw["fields"],
            dtype="float32",
        )

    api.features = empty
    result = read_qlib_prices(
        data_dir=provider, start="1990-01-01", end="1990-01-02", market="all"
    )
    assert result.empty and result.index.names == ["date", "ticker"]
    assert isinstance(result.index.get_level_values("date"), pd.DatetimeIndex)
    assert "extra_metric" in result and result["close"].dtype == np.float32


@pytest.mark.parametrize(
    "args,error",
    [
        ({}, ValueError),
        ({"tickers": [], "market": "all"}, ValueError),
        ({"tickers": []}, ValueError),
        ({"tickers": ["SH600000", "sh600000"]}, ValueError),
        ({"tickers": [None]}, TypeError),
        ({"tickers": "../../escape"}, ValueError),
        ({"market": "../all"}, ValueError),
        ({"market": 1}, TypeError),
        ({"tickers": "UNKNOWN"}, FileNotFoundError),
        ({"market": "missing"}, FileNotFoundError),
    ],
)
def test_invalid_selector(provider, args, error):
    with pytest.raises(error):
        read_qlib_prices(
            data_dir=provider, start="2024-01-02", end="2024-01-04", **args
        )


@pytest.mark.parametrize(
    "start,end",
    [
        ("2024-01-04", "2024-01-02"),
        ("NaT", "2024-01-04"),
        ("2024-01-02T12:00", "2024-01-04"),
        ("2024-01-02T00:00Z", "2024-01-04"),
    ],
)
def test_invalid_dates(provider, start, end):
    with pytest.raises(ValueError):
        read_qlib_prices(data_dir=provider, start=start, end=end, tickers="SH600000")


def test_missing_optional_dependency_has_install_hint(provider, monkeypatch):
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "qlib":
            raise ModuleNotFoundError("No module named qlib", name="qlib")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(ImportError, match=r"quanttoolskit\[qlib\]"):
        read_qlib_prices(
            data_dir=provider, start="2024-01-02", end="2024-01-04", market="all"
        )


def test_base_package_import_does_not_import_qlib():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import quanttoolskit.data as d; "
            "assert 'qlib' not in sys.modules; assert callable(d.read_qlib_prices); "
            "assert callable(d.save_qlib_prices); "
            "assert not hasattr(d, 'load_qlib_prices')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def prices():
    return to_date_ticker_frame(
        df=pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "ticker": ["SH600000", "SZ000001"],
                "close": np.array([1.5, np.nan], dtype="float32"),
                "adjclose": np.array([15.0, 30.0], dtype="float32"),
                "extra_metric": np.array([0.123456789012345, np.nan], dtype="float64"),
            }
        )
    )


def query(db):
    with duckdb.connect(str(db), read_only=True) as con:
        raw = con.execute(
            "SELECT * EXCLUDE (release_tag) FROM qlib_prices ORDER BY date,ticker"
        ).df()
    return to_date_ticker_frame(df=raw)


def test_save_sql_roundtrip_precision_nulls_and_no_mutation(tmp_path, prices):
    db = tmp_path / "nested" / "data.duckdb"
    original = prices.copy(deep=True)
    save_qlib_prices(db=db, prices=prices, release_tag="2026-10-07")
    pd.testing.assert_frame_equal(
        query(db), prices, check_index_type=False, check_exact=True
    )
    pd.testing.assert_frame_equal(prices, original)
    with duckdb.connect(str(db)) as con:
        assert con.execute(
            "SELECT DISTINCT release_tag FROM qlib_prices"
        ).fetchall() == [("2026-10-07",)]
        assert (
            con.execute(
                "SELECT COUNT(*) FROM qlib_prices WHERE close IS NULL"
            ).fetchone()[0]
            == 1
        )
        assert con.execute(
            "SELECT constraint_column_names FROM duckdb_constraints() "
            "WHERE constraint_type='PRIMARY KEY'"
        ).fetchone()[0] == ["date", "ticker"]
        assert con.execute("DESCRIBE qlib_prices").fetchall()[2][1] == "FLOAT"


def test_replace_removes_old_rows_columns_and_release_but_preserves_other_tables(
    tmp_path, prices
):
    db = tmp_path / "data.duckdb"
    save_qlib_prices(db=db, prices=prices, release_tag="2026-10-07")
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE prices AS SELECT 42 AS sentinel")
    replacement = prices.iloc[:1].drop(columns="extra_metric")
    save_qlib_prices(db=db, prices=replacement, release_tag="2026-10-08")
    pd.testing.assert_frame_equal(
        query(db), replacement, check_index_type=False, check_exact=True
    )
    with duckdb.connect(str(db)) as con:
        assert con.execute("SELECT sentinel FROM prices").fetchone()[0] == 42
        assert con.execute(
            "SELECT DISTINCT release_tag FROM qlib_prices"
        ).fetchall() == [("2026-10-08",)]


def test_error_after_table_recreation_rolls_back_old_schema_and_data(
    tmp_path, prices, monkeypatch
):
    db = tmp_path / "data.duckdb"
    save_qlib_prices(db=db, prices=prices, release_tag="2026-10-07")
    monkeypatch.setattr(
        writer,
        "QLIB_PRICES_CONSTRAINTS",
        (
            *writer.QLIB_PRICES_CONSTRAINTS,
            "SELECT * FROM missing_table",
        ),
    )
    with pytest.raises(duckdb.Error):
        save_qlib_prices(
            db=db,
            prices=prices.iloc[:1].drop(columns="adjclose"),
            release_tag="2026-10-08",
        )
    pd.testing.assert_frame_equal(
        query(db), prices, check_index_type=False, check_exact=True
    )
    with duckdb.connect(str(db)) as con:
        assert con.execute(
            "SELECT DISTINCT release_tag FROM qlib_prices"
        ).fetchall() == [("2026-10-07",)]


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.iloc[:0],
        lambda p: pd.concat([p, p]),
        lambda p: p.iloc[::-1],
        lambda p: p.assign(release_tag=1),
        lambda p: p.assign(CLOSE=1),
        lambda p: p.assign(close="not numeric"),
        lambda p: p.assign(close=np.inf),
        lambda p: p.assign(close=complex(1, 2)),
        lambda p: p.reset_index(),
    ],
)
def test_invalid_input_cannot_replace_old_table(tmp_path, prices, change):
    db = tmp_path / "data.duckdb"
    save_qlib_prices(db=db, prices=prices, release_tag="2026-10-07")
    with pytest.raises(ValueError):
        save_qlib_prices(db=db, prices=change(prices), release_tag="2026-10-08")
    pd.testing.assert_frame_equal(
        query(db), prices, check_index_type=False, check_exact=True
    )


@pytest.mark.parametrize("tag", ["latest", "2026-02-30", "2026-1-1", "../../escape"])
def test_invalid_release_tag_does_not_create_database(tmp_path, prices, tag):
    db = tmp_path / "data.duckdb"
    with pytest.raises(ValueError):
        save_qlib_prices(db=db, prices=prices, release_tag=tag)
    assert not db.exists()


@pytest.mark.skipif(not HAS_QLIB, reason="需要 qlib 可选依赖")
def test_real_qlib_binary_read_market_and_empty(provider, tmp_path):
    frame = read_qlib_prices(
        data_dir=provider, start="2024-01-02", end="2024-01-04", market="all"
    )
    assert frame.shape == (6, 11)
    assert frame.loc[(pd.Timestamp("2024-01-04"), "SZ000001"), "adjclose"] == 6
    assert frame.loc[(slice(None), "SZ000001"), "extra_metric"].isna().all()
    assert frame.loc[pd.Timestamp("2024-01-03"), "close"].isna().all()
    selected = read_qlib_prices(
        data_dir=provider, start="2024-01-02", end="2024-01-04", market="csi300"
    )
    assert selected.index.tolist() == [
        (pd.Timestamp("2024-01-02"), "SH600000"),
        (pd.Timestamp("2024-01-03"), "SZ000001"),
        (pd.Timestamp("2024-01-04"), "SZ000001"),
    ]
    assert read_qlib_prices(
        data_dir=provider, start="1990-01-01", end="1990-01-02", market="all"
    ).empty
    db = tmp_path / "real.duckdb"
    save_qlib_prices(db=db, prices=frame, release_tag="2026-10-07")
    pd.testing.assert_frame_equal(
        query(db), frame, check_index_type=False, check_exact=True
    )


@pytest.mark.skipif(not HAS_QLIB, reason="需要 qlib 可选依赖")
def test_runnable_example_uses_manual_sql_and_temporary_database(provider):
    import json

    (provider.parent / "qlib_bin.manifest.json").write_text(
        json.dumps({"release_tag": "2026-10-07"})
    )
    example = Path(__file__).resolve().parents[1] / "examples/qlib_community_data.py"
    result = subprocess.run(
        [
            sys.executable,
            str(example),
            "--data-dir",
            str(provider),
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-04",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SQL 往返验证通过" in result.stdout
    assert "rows: 6" in result.stdout and "extra_metric" in result.stdout
    assert not list(provider.parent.glob("*.duckdb"))
