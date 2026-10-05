import inspect
import json
import sys
import zipfile
from datetime import date
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest

from quanttoolskit.data import (
    SP500Data,
    load_constituents,
    load_fundamentals,
    load_fundamentals_panel,
    load_fundamentals_pit,
    load_fundamentals_ttm,
    load_members,
    load_prices,
    prepare_members,
)


@pytest.fixture
def local_source(tmp_path):
    universe = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "name": ["Apple", "Microsoft"],
            "cik": ["0000320193", "0000789019"],
        }
    )
    archive = tmp_path / "facts.zip"
    periods = [
        ("2024-03-31", 100, "2024-05-01", "10-Q"),
        ("2024-06-30", 250, "2024-08-01", "10-Q"),
        ("2024-09-30", 400, "2024-11-01", "10-Q"),
        ("2024-12-31", 600, "2025-02-01", "10-K"),
    ]
    with zipfile.ZipFile(archive, "w") as z:
        for row in universe.itertuples():
            items = [
                {
                    "start": "2024-01-01",
                    "end": end,
                    "val": value,
                    "filed": filed,
                    "accn": str(i),
                    "form": form,
                    "fy": 2024,
                    "fp": "FY",
                }
                for i, (end, value, filed, form) in enumerate(periods)
            ]
            # Later restatement must not contaminate quarters published earlier.
            items.append(dict(items[0], val=110, filed="2025-03-01", accn="restated"))
            invalid = {
                "end": "2025-12-31",
                "val": 1,
                "filed": "2024-05-01",
                "accn": "invalid",
                "form": "10-Q",
                "fy": 2024,
                "fp": "Q1",
            }
            body = {
                "cik": int(row.cik),  # type: ignore
                "facts": {
                    "us-gaap": {
                        "NetIncomeLoss": {"units": {"USD": items}},
                        "Revenues": {"units": {"USD": items}},
                        "Assets": {"units": {"USD": [invalid]}},
                    }
                },
            }
            z.writestr("CIK" + row.cik + ".json", json.dumps(body))  # type: ignore
    return universe, archive, tmp_path / "market.db"


def test_no_write_full_interface_and_fixed_universe(local_source, monkeypatch):
    universe, archive, db = local_source
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    universe.loc[0, "ticker"] = "CHANGED"
    assert "CHANGED" not in data.members(write=False).ticker.tolist()
    monkeypatch.setattr(
        duckdb,
        "connect",
        lambda *a, **k: pytest.fail("read-only extraction connected to DB"),
    )
    result = data.fundamentals(write=False)
    assert not db.exists()
    assert set(result.ticker) == {"AAPL", "MSFT"}
    assert "fields" not in inspect.signature(data.fundamentals).parameters
    assert "tickers" not in inspect.signature(data.fundamentals).parameters
    quarters = result[
        (result.ticker == "AAPL") & (result.field == "net_income") & result.derived
    ]
    assert quarters.value.tolist() == [150, 150, 200]
    assert len(data.quarantine) == 2
    assert (result.period_end <= result.filed).all()


def test_write_repeat_pit_ttm_and_member_snapshot(local_source):
    universe, archive, db = local_source
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    expected = data.fundamentals()
    pd.testing.assert_frame_equal(expected, data.fundamentals())
    data.members()
    with duckdb.connect(str(db)) as c:
        assert c.execute("SELECT count(*) FROM fundamentals").fetchone()[0] == len(  # type: ignore
            expected
        )
        assert c.execute("SELECT count(*) FROM constituents").fetchone()[0] == 2  # type: ignore
    pit = load_fundamentals_pit(
        "2024-08-01", tickers="AAPL", fields="net_income", period_months=3, db=str(db)
    )
    assert pit.iloc[0].value == 150
    assert (pit.filed <= pd.Timestamp("2024-08-01")).all()
    ttm = load_fundamentals_ttm(
        ["2025-02-01"], tickers="AAPL", fields="net_income", db=str(db)
    )
    assert ttm.iloc[0].value == 600
    with pytest.raises(ValueError, match="TTM"):
        load_fundamentals_ttm(["2025-02-01"], fields="eps_basic", db=str(db))
    assert load_fundamentals_pit("2025-02-01", tickers=[], db=str(db)).empty


def test_missing_member_does_not_clear_old_values(local_source, tmp_path):
    universe, archive, db = local_source
    original = SP500Data(
        universe=universe, companyfacts=archive, db=db, write=True
    ).fundamentals()
    incomplete = tmp_path / "missing.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(incomplete, "w") as target:
        filename = "CIK0000320193.json"
        target.writestr(filename, source.read(filename))
    data = SP500Data(universe=universe, companyfacts=incomplete, db=db, write=True)
    with pytest.raises(ValueError, match="来源不完整"):
        data.fundamentals()
    partial = data.fundamentals(allow_partial=True)
    assert set(partial.ticker) == {"AAPL"}
    with duckdb.connect(str(db)) as c:
        assert c.execute("SELECT count(*) FROM fundamentals").fetchone()[0] == len(  # type: ignore
            original
        )


def test_write_failure_rolls_back_delete(local_source):
    universe, archive, db = local_source
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    out = data.fundamentals()
    with duckdb.connect(str(db)) as c:
        c.execute("DROP TABLE fundamentals_quarantine")
        c.execute("CREATE TABLE fundamentals_quarantine (wrong INTEGER)")
    with pytest.raises(duckdb.Error):
        data.fundamentals()
    with duckdb.connect(str(db)) as c:
        assert c.execute("SELECT count(*) FROM fundamentals").fetchone()[0] == len(out)  # type: ignore


def test_members_mapping_conflict_and_share_classes(tmp_path):
    members = tmp_path / "members.csv"
    sec = tmp_path / "sec.json"
    members.write_text(
        "ticker,name,cik\nBRK.B,Berkshire B,1067983\nBRK.A,Berkshire A,1067983\n"
    )
    sec.write_text(
        json.dumps(
            {
                str(i): {"ticker": ticker, "cik_str": 1067983, "title": "Berkshire"}
                for i, ticker in enumerate(["BRK-A", "BRK-B"])
            }
        )
    )
    universe = load_members(members, sec_tickers=sec)
    assert universe.ticker.tolist() == ["BRK-A", "BRK-B"]
    assert universe.cik.tolist() == ["0001067983"] * 2
    members.write_text("ticker,name,cik\nBRK.B,Berkshire B,123\n")
    with pytest.raises(ValueError, match="冲突"):
        load_members(members, sec_tickers=sec)


def test_prices_shared_universe_and_optional_write(local_source, monkeypatch):
    universe, archive, db = local_source
    requested = []

    def download(tickers, **kwargs):
        requested.extend(tickers)
        assert kwargs["auto_adjust"] is False
        columns = pd.MultiIndex.from_product([["AAPL"], ["Close", "Open"]])
        return pd.DataFrame(
            [[10, 9]],
            index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
            columns=columns,
        )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    data = SP500Data(universe=universe, companyfacts=archive, db=db)
    result = data.prices("2024-01-01", "2024-02-01")
    assert not db.exists()
    assert requested == ["AAPL", "MSFT"]
    assert data.report["missing_tickers"] == ["MSFT"]
    pd.testing.assert_frame_equal(
        result, data.prices("2024-01-01", "2024-02-01", write=True)
    )
    assert load_prices(db=db, tickers="AAPL").iloc[0]["close"] == 10
    data.prices("2024-01-01", "2024-02-01", write=True)
    assert len(load_prices(db=db)) == 1
    with pytest.raises(ValueError, match="end"):
        data.prices("2024-02-01", "2024-01-01")


def test_wikipedia_refresh_parses_members_and_checks_sec(tmp_path, monkeypatch):
    from io import BytesIO

    from quanttoolskit.data.sources import wikipedia

    html = """<table><tr><th>Unrelated</th></tr><tr><td>ignore</td></tr></table>
    <table><tr><th>Symbol</th><th>Security</th><th>CIK</th><th>Date added</th></tr>
    <tr><td>AAPL[1]</td><td>Apple Inc.</td><td>320193</td>
    <td>1982-11-30</td></tr></table>"""
    monkeypatch.setattr(wikipedia, "urlopen", lambda *a, **k: BytesIO(html.encode()))
    sec = tmp_path / "tickers.json"
    sec.write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}})
    )
    first_use = prepare_members()  # 首次调用无成员文件和 SEC JSON 参数。
    assert first_use.cik.tolist() == ["0000320193"]
    assert "sec_title" not in first_use.columns
    universe = prepare_members(sec_tickers=sec)
    assert universe.ticker.tolist() == ["AAPL"]
    assert universe.cik.tolist() == ["0000320193"]
    assert universe.iloc[0].date_added == pd.Timestamp("1982-11-30")


def test_database_errors_are_not_hidden_as_empty_data(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fundamentals_pit("2025-01-01", db=tmp_path / "absent.db")
    db = tmp_path / "no_fundamentals.db"
    with duckdb.connect(str(db)) as c:
        c.execute("CREATE TABLE unrelated (value INTEGER)")
    with pytest.raises(duckdb.Error):
        load_fundamentals_pit("2025-01-01", db=db)


def test_members_have_explicit_schema_and_upgrade_old_snapshot(local_source):
    from quanttoolskit.data import load_constituents

    universe, archive, db = local_source
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE constituents (ticker VARCHAR, name VARCHAR)")
        con.execute("INSERT INTO constituents VALUES ('OLD', 'Old company')")
        con.execute("CREATE TABLE prices (sentinel INTEGER)")
        con.execute("INSERT INTO prices VALUES (42)")
    universe["date_added"] = ["1982-11-30", "1994-06-01"]
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    data.members()
    data.members()
    result = load_constituents(db=db)
    assert result.ticker.tolist() == ["AAPL", "MSFT"]
    assert result.cik.tolist() == ["0000320193", "0000789019"]
    assert result.sector.isna().all()
    with duckdb.connect(str(db)) as con:
        columns = {
            row[0]: row for row in con.execute("DESCRIBE constituents").fetchall()
        }
        assert columns["ticker"][3] == "PRI"
        assert columns["name"][2] == "NO"
        assert columns["date_added"][1] == "DATE"
        assert columns["cik"][1] == "VARCHAR"
        assert con.execute("SELECT * FROM prices").fetchone() == (42,)


@pytest.mark.parametrize("suffix", ["csv", "parquet"])
def test_load_snapshot_needs_no_network_or_sec_file(tmp_path, monkeypatch, suffix):
    from quanttoolskit.data import universe as module

    monkeypatch.setattr(
        module,
        "fetch_current_constituents",
        lambda: pytest.fail("snapshot loading requested network"),
    )
    snapshot = pd.DataFrame(
        {
            "ticker": ["BRK.B"],
            "name": ["Berkshire B"],
            "cik": ["0001067983"],
            "sec_cik": ["0001067983"],
            "sec_title": ["Berkshire"],
        }
    )
    path = tmp_path / f"members.{suffix}"
    if suffix == "csv":
        snapshot.to_csv(path, index=False)
    else:
        snapshot.to_parquet(path, index=False)
    result = load_members(path)
    assert result.ticker.tolist() == ["BRK-B"]
    assert result.cik.tolist() == ["0001067983"]
    assert result.sec_cik.tolist() == ["0001067983"]
    assert result.attrs["source"] == str(path)


def test_optional_sec_mapping_fills_missing_cik(tmp_path):
    path = tmp_path / "members.csv"
    path.write_text("ticker,name\nAAPL,Apple\n")
    assert load_members(path).cik.isna().all()
    sec = tmp_path / "tickers.json"
    sec.write_text(
        json.dumps({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}})
    )
    assert load_members(path, sec_tickers=sec).cik.tolist() == ["0000320193"]


def test_prices_only_without_cik_creates_directory(tmp_path, monkeypatch):
    from quanttoolskit.data.sources import yahoo

    requested = []

    def download(tickers, **kwargs):
        requested.append(tickers)
        return pd.DataFrame(
            {"Close": [10]}, index=pd.DatetimeIndex(["2024-01-02"], name="Date")
        )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    db = tmp_path / "new" / "nested" / "market.db"
    universe = pd.DataFrame({"ticker": [" brk.b "], "name": ["Berkshire B"]})
    data = SP500Data(universe=universe, db=db, write=True)
    assert not db.parent.exists()  # 构造与只返回成员都不产生文件。
    assert data.members(write=False).cik.isna().all()
    data.prices("2024-01-01", "2024-02-01")
    assert requested == [["BRK-B"]]
    data.members()
    assert load_prices(db=db, tickers="brk.b").ticker.tolist() == ["BRK-B"]
    assert load_prices(db=db).adj_close.isna().all()  # 不以未复权 close 冒充复权价。
    assert load_constituents(db=db, tickers=" brk.b ").ticker.tolist() == ["BRK-B"]
    with pytest.raises(ValueError, match="证券身份"):
        yahoo.get_prices(["BRK-B", "AAPL"], "2024-01-01")


@pytest.mark.parametrize("first_method", ["members", "fundamentals"])
def test_other_writers_create_directory(local_source, tmp_path, first_method):
    universe, archive, _ = local_source
    db = tmp_path / first_method / "new.db"
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    getattr(data, first_method)()
    assert db.exists()
    if first_method == "fundamentals":
        assert not load_fundamentals(db=db, tickers=" aapl ").empty


@pytest.mark.parametrize("allow_partial", [False, True])
def test_malformed_sec_payload_cannot_clear_history(
    local_source, tmp_path, allow_partial
):
    universe, archive, db = local_source
    original = SP500Data(
        universe=universe, companyfacts=archive, db=db, write=True
    ).fundamentals()
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(broken, "w") as target:
        for filename in source.namelist():
            body = json.loads(source.read(filename))
            if body["cik"] == 789019:
                del body["facts"]
            target.writestr(filename, json.dumps(body))
    data = SP500Data(universe=universe, companyfacts=broken, db=db, write=True)
    with pytest.raises(ValueError, match="companyfacts 结构"):
        data.fundamentals(allow_partial=allow_partial)
    assert data.report["written"] is False
    assert len(load_fundamentals(db=db)) == len(original)


def test_ttm_rejects_nonconsecutive_quarters_even_with_valid_total_span(local_source):
    universe, archive, db = local_source
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)
    data.fundamentals()
    # 首尾仍相隔 275 天，旧逻辑会把中间重复覆盖或缺失的季度凑成 TTM。
    with duckdb.connect(str(db)) as con:
        con.execute(
            "DELETE FROM fundamentals WHERE ticker='AAPL' AND field='net_income'"
        )
        for end in ["2024-03-31", "2024-04-30", "2024-05-31", "2024-12-31"]:
            con.execute(
                """INSERT INTO fundamentals
                (ticker,field,period_end,period_months,value,accn,filed,derived)
                VALUES ('AAPL','net_income',?,3,100,?,'2025-02-01',false)""",
                [end, end],
            )
    result = load_fundamentals_ttm(["2025-02-01"], fields="net_income", db=db)
    assert result.ticker.tolist() == ["MSFT"]
    assert result.value.tolist() == [600]


def test_csv_preserves_na_ticker_and_empty_cik(tmp_path):
    path = tmp_path / "members.csv"
    path.write_text("ticker,name,cik\nNA,National Bank,\n")
    members = load_members(path)
    assert members.ticker.tolist() == ["NA"]
    assert members.cik.isna().all()


def test_fetch_sp500_tables_parses_changes_and_preserves_na_ticker(monkeypatch):
    from io import BytesIO

    from quanttoolskit.data.sources import wikipedia

    current_html = """<table>
    <tr><th>Symbol</th><th>Security</th></tr>
    <tr><td>AAPL</td><td>Apple Inc.</td></tr>
    <tr><td>NA</td><td>National Bank</td></tr></table>"""
    changes_html = """<table>
    <tr><th>Effective Date</th><th>Added Ticker</th><th>Added Security</th>
    <th>Removed Ticker</th><th>Removed Security</th><th>Reason</th></tr>
    <tr><td>January 22, 2024</td><td>XYZ[1]</td><td>Xyz Corp</td>
    <td>ABC</td><td>Abc Corp</td><td>Replacement</td></tr>
    <tr><td>not a date</td><td>QQQ</td><td>Q Corp</td>
    <td>WWW</td><td>W Corp</td><td>ignored</td></tr></table>"""

    def fake_urlopen(request, timeout=None):
        target = getattr(request, "full_url", str(request))
        page = changes_html if "Historical" in target else current_html
        return BytesIO(page.encode())

    monkeypatch.setattr(wikipedia, "urlopen", fake_urlopen)
    current, changes = wikipedia.fetch_sp500_tables(
        "https://example.org/current",
        "https://example.org/Historical_components_of_the_S%26P_500",
    )
    # "NA" 是合法证券代码, 不能当缺失丢掉: 与 load_members 的 CSV 入口同一口径。
    assert current.ticker.tolist() == ["AAPL", "NA"]
    assert changes.added_ticker.tolist() == ["XYZ"]
    assert changes.removed_ticker.tolist() == ["ABC"]
    assert changes.date.tolist() == [pd.Timestamp("2024-01-22")]


def test_readers_reject_unknown_field_names(local_source):
    universe, archive, db = local_source
    SP500Data(universe=universe, companyfacts=archive, db=db, write=True).fundamentals()
    for call in (
        lambda: load_fundamentals(fields=["revenu"], db=db),
        lambda: load_fundamentals_pit("2025-01-01", fields="revenu", db=db),
        lambda: load_fundamentals_panel(["2025-01-01"], fields="revenu", db=db),
        lambda: load_fundamentals_ttm(["2025-01-01"], fields="revenu", db=db),
    ):
        with pytest.raises(KeyError, match="revenu"):
            call()


def test_reader_filters_accept_numpy_scalars_and_iterators(local_source):
    import numpy as np

    universe, archive, db = local_source
    SP500Data(universe=universe, companyfacts=archive, db=db, write=True).fundamentals()
    pit = load_fundamentals_pit(
        "2025-01-01",
        tickers=(ticker for ticker in ["aapl"]),
        fields="net_income",
        period_months=np.int64(3),
        db=db,
    )
    assert pit.ticker.tolist() == ["AAPL"]
    assert load_fundamentals(tickers="", db=db).empty


def test_pit_max_staleness_days(local_source):
    universe, archive, db = local_source
    SP500Data(universe=universe, companyfacts=archive, db=db, write=True).fundamentals()
    assert not load_fundamentals_pit("2025-06-30", tickers="AAPL", db=db).empty
    # 最近一期 period_end 是 2024-12-31, 距 2025-06-30 有 181 天。
    assert load_fundamentals_pit(
        "2025-06-30", tickers="AAPL", max_staleness_days=30, db=db
    ).empty
    assert not load_fundamentals_pit(
        "2025-06-30", tickers="AAPL", max_staleness_days=365, db=db
    ).empty


def test_library_logging_is_opt_in(tmp_path):
    import subprocess

    path = tmp_path / "logs" / "market.db"
    body = (
        "from pathlib import Path\n"
        "from quanttoolskit.data import get_duckdb\n"
        f"get_duckdb(path=Path({str(path)!r}), read_only=False)\n"
    )
    # 默认安静: 库不替使用方往 stderr 打日志。
    silent = subprocess.run(
        [sys.executable, "-c", body], capture_output=True, text=True
    )
    assert silent.returncode == 0, silent.stderr
    assert silent.stderr == ""

    # import 之后显式 enable 才输出。
    noisy = subprocess.run(
        [
            sys.executable,
            "-c",
            "import quanttoolskit\n"
            "from loguru import logger\n"
            'logger.enable("quanttoolskit")\n' + body,
        ],
        capture_output=True,
        text=True,
    )
    assert noisy.returncode == 0, noisy.stderr
    assert "正在连接 DuckDB" in noisy.stderr


def test_report_marks_its_source(local_source, monkeypatch):
    universe, archive, db = local_source
    data = SP500Data(universe=universe, companyfacts=archive, db=db, write=True)

    def download(tickers, **kwargs):
        columns = pd.MultiIndex.from_product([["AAPL"], ["Close", "Open"]])
        return pd.DataFrame(
            [[10, 9]],
            index=pd.DatetimeIndex(["2024-01-02"], name="Date"),
            columns=columns,
        )

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    data.prices("2024-01-01", "2024-02-01")
    assert data.report["kind"] == "prices"
    data.fundamentals()
    assert data.report["kind"] == "fundamentals"
    # 两种来源都有这组公共键, 不会读到一半才发现缺键。
    assert {"kind", "written", "rows"} <= data.report.keys()


def test_save_prices_replaces_whole_row(tmp_path):
    from quanttoolskit.data.schema import PRICES_DDL
    from quanttoolskit.data.writer import save_prices

    db = tmp_path / "prices.db"
    with duckdb.connect(str(db)) as con:
        con.execute(PRICES_DDL)
        con.execute("ALTER TABLE prices ADD COLUMN source VARCHAR")
        con.execute(
            "INSERT INTO prices (date,ticker,close,source) "
            "VALUES ('2024-01-02','AAPL',9,'manual')"
        )
    save_prices(
        db,
        pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "ticker": ["AAPL", "AAPL"],
                "open": [10, 11],
                "high": [10, 11],
                "low": [10, 11],
                "close": [10, 11],
                "adj_close": [None, 11],
                "volume": [5, 6],
            }
        ),
    )
    with duckdb.connect(str(db)) as con:
        rows = con.execute(
            "SELECT date, close, volume, source FROM prices ORDER BY date"
        ).fetchall()
    # 命中的行整行替换, 多出来的列不保留旧值(INSERT OR REPLACE 会保留)。
    assert rows == [
        (date(2024, 1, 2), 10.0, 5.0, None),
        (date(2024, 1, 3), 11.0, 6.0, None),
    ]
