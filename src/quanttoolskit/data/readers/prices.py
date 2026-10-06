"""按证券和日期读取日行情。"""

from pathlib import Path

from ..connection import get_duckdb
from ..universe import normalize_sec_ticker


def load_prices(*, db: str | Path, tickers=None, start=None, end=None):
    """从 DuckDB 读取日行情, 不发起下载。

    Args:
        db: 数据库文件路径, 以只读方式打开。
        tickers: 单个 ticker 或序列；统一大写和短横线, None 不限, 空序列不匹配。
        start: 日期下限, 含当日；None 不限。
        end: 日期上限, 含当日；None 不限。与 Yahoo 获取接口的排他 end 不同。

    Returns:
        保存的行情列, 按 ticker/date 升序；匹配不到时返回保留列结构的空表。

    Raises:
        FileNotFoundError: 数据库文件不存在。
        duckdb.Error: 表缺失、结构不兼容或查询失败, 不转换成空结果。
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
    for column, op, value in [("date", ">=", start), ("date", "<=", end)]:
        if value is not None:
            clauses.append(f"{column} {op} ?")
            params.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with get_duckdb(path=Path(db)) as con:
        return con.execute(
            "SELECT * FROM prices" + where + " ORDER BY ticker,date", params
        ).df()
