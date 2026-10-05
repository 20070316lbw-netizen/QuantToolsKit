"""读取当前完整成员快照。"""

from pathlib import Path

from ..connection import get_duckdb
from ..universe import normalize_sec_ticker


def load_constituents(*, db: str | Path, tickers=None):
    """读取已保存的当前成员快照，不刷新网页、不反推历史成员。

    Args:
        db: DuckDB 文件路径，以只读方式打开。
        tickers: 单个 ticker 或序列；统一大写和短横线，None 不限，空序列不匹配。

    Returns:
        数据库实际保存的全部成员列，按 ticker 排序。旧库若仍是两列结构，
        则返回已有列；完整新结构由 members(write=True) 保存。

    Raises:
        FileNotFoundError: 数据库文件不存在。
        duckdb.Error: 表缺失或查询失败，不转换成空结果。
    """
    clauses, params = [], []
    if tickers is not None:
        symbols = [tickers] if isinstance(tickers, str) else list(tickers)
        symbols = [normalize_sec_ticker(ticker) for ticker in symbols]
        if not symbols:
            clauses.append("FALSE")
        else:
            clauses.append("ticker IN (" + ",".join("?" for _ in symbols) + ")")
            params.extend(symbols)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_duckdb(path=Path(db)) as con:
        return con.execute(
            "SELECT * FROM constituents" + where + " ORDER BY ticker", params
        ).df()
