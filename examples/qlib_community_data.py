"""社区行情读取、保存及手写 SQL 示例。

运行: python examples/qlib_community_data.py --data-dir <发布目录>/cn_data。
默认只写临时数据库；显式 --db 路径会整表替换其中的 qlib_prices。
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd

from quanttoolskit.data import (
    get_duckdb,
    read_qlib_prices,
    save_qlib_prices,
    to_date_ticker_frame,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path, help="指定后会整表替换 qlib_prices")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-12-31")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--tickers", nargs="+")
    selector.add_argument("--market")
    args = parser.parse_args()
    root = args.data_dir.expanduser().resolve()
    manifest = json.loads((root.parent / "qlib_bin.manifest.json").read_text())
    tickers = args.tickers
    if tickers is None and args.market is None:
        tickers = ["SH600000", "SZ000001"]
    prices = read_qlib_prices(
        data_dir=root,
        start=args.start,
        end=args.end,
        tickers=tickers,
        market=args.market,
    )
    with tempfile.TemporaryDirectory(prefix="qlib-example-") as folder:
        db = args.db or Path(folder) / "qlib_cn.duckdb"
        save_qlib_prices(db=db, prices=prices, release_tag=manifest["release_tag"])
        # 查询直接使用 SQL；来源列不是计算字段, 转换前排除它。
        with get_duckdb(path=db) as con:
            raw = con.execute(
                "SELECT * EXCLUDE (release_tag) FROM qlib_prices ORDER BY date,ticker"
            ).df()
        stored = to_date_ticker_frame(df=raw)
        pd.testing.assert_frame_equal(
            prices,
            stored,
            check_index_type=False,
            check_exact=True,
        )
        print(f"release_tag: {manifest['release_tag']}")
        print(f"rows: {len(stored)}, fields: {stored.columns.tolist()}")
        print(stored.head().to_string())
        print("SQL 往返验证通过", f"db: {db}" if args.db else "（临时数据库）")


if __name__ == "__main__":
    main()
