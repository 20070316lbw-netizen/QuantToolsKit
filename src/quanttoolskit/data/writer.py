"""DuckDB 事务写入：基本面范围替换、当前成员快照替换、行情按主键更新。

这些函数由 SP500Data 的写入开关调用, 不负责获取数据或选择 universe。
各次写入独立提交；成员、行情与基本面之间没有跨方法的大事务。
任何事务内错误都会回滚并向外抛出, 不能把部分结果当作更新成功。
"""

from pathlib import Path

import pandas as pd

from .connection import get_duckdb
from .schema import CONSTITUENTS_COLUMNS, CONSTITUENTS_DDL, DDL, PRICES_DDL


def save_fundamentals(
    path: Path,
    facts: pd.DataFrame,
    quarantine: pd.DataFrame,
    tickers: list[str],
    fields: list[str],
) -> None:
    """替换成功读取的 ticker/field 范围, 原子保存有效事实和隔离事实。

    Args:
        path: DuckDB 文件路径, 写入时自动创建父目录和文件。
        facts: 已标准化、按版本主键去重的有效基本面长表。
        quarantine: 与 facts 同列结构的异常事实, 可为空。
        tickers: 已完整读取全部所需 CIK 的证券列表；缺来源的证券不得传入。
        fields: 本次管理的标准字段列表, 和 tickers 组成替换范围。

    Notes:
        范围内先删后插, 可以清除新快照里已不存在的旧事实。即使某个字段此次无行,
        其旧值也会移除；范围外数据保留。删除、有效值与隔离值插入在同一事务中。
        不写入完整原始 XBRL 长表, 完整来源由本地 ZIP 保留。
    """
    with get_duckdb(path=path, read_only=False) as con:
        con.execute("BEGIN")
        try:
            con.execute(DDL)
            con.register("_facts", facts)
            con.register("_rejected", quarantine)
            # 替换范围来自成功的证券列表, 不从有值的行反推, 否则无法清除缺失字段旧值。
            con.register(
                "_scope",
                pd.DataFrame(
                    [(t, f) for t in tickers for f in fields],
                    columns=["ticker", "field"],
                ),
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS fundamentals_quarantine "
                "AS SELECT * FROM fundamentals LIMIT 0"
            )
            for table in ("fundamentals", "fundamentals_quarantine"):
                con.execute(
                    f"DELETE FROM {table} USING _scope s "
                    f"WHERE {table}.ticker=s.ticker AND {table}.field=s.field"
                )
            con.execute("INSERT INTO fundamentals BY NAME SELECT * FROM _facts")
            con.execute(
                "INSERT INTO fundamentals_quarantine BY NAME SELECT * FROM _rejected"
            )
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


def save_members(path: Path, members: pd.DataFrame) -> None:
    """校验并替换当前成员快照, 使用 schema 的固定列和类型。

    Args:
        path: DuckDB 文件路径。
        members: 完整当前快照, ticker/name 必须有效且 ticker 唯一。可选成员列缺失
            时补 NULL, 仅保存 CONSTITUENTS_COLUMNS 中的列, date_added 转为 DATE。

    Raises:
        ValueError: 必需值无效、快照为空、ticker 重复或日期无法转换。
        duckdb.Error: 建表或插入失败；事务回滚, 旧快照保留。

    Notes:
        这是整张当前名单替换, 不是逐行 upsert。行情、基本面历史和历史成员关系
        不随成员退出而删除；CIK 保持字符串, 不以它作为证券主键。
    """
    data = members.copy()
    for column in ("ticker", "name"):
        if column not in data or data[column].isna().any():
            raise ValueError(f"成员快照缺少有效的 {column}")
        if data[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"成员快照的 {column} 不得为空")
    if data.empty or data.ticker.duplicated().any():
        raise ValueError("成员快照为空或 ticker 重复")
    for column in CONSTITUENTS_COLUMNS:
        if column not in data:
            data[column] = None
    data = data[list(CONSTITUENTS_COLUMNS)]
    data["date_added"] = pd.to_datetime(data.date_added).dt.date
    with get_duckdb(path=path, read_only=False) as con:
        con.execute("BEGIN")
        try:
            con.register("_members", data)
            con.execute(CONSTITUENTS_DDL)
            con.execute("INSERT INTO constituents BY NAME SELECT * FROM _members")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


def save_prices(path: Path, prices: pd.DataFrame) -> None:
    """按 ticker/date 主键更新行情, 未返回的证券和日期保留旧值。

    Args:
        path: DuckDB 文件路径。
        prices: 包含 date/ticker/open/high/low/close/adj_close/volume 的日行情长表。
            date 转成 DATE, close 不得为空, 同一批次不能有重复 ticker/date。

    Raises:
        ValueError: 批次主键重复、close 缺失或日期无法转换。
        duckdb.Error: 事务写入失败, 原数据回滚保留。

    Notes:
        此处只存储, 不填补停牌日期、不删除缺行情证券, 也不计算复权价格。
    """
    columns = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    data = prices[columns].copy()
    data["date"] = pd.to_datetime(data.date).dt.date
    if data.duplicated(["ticker", "date"]).any():
        raise ValueError("行情包含重复 ticker/date")
    if data.close.isna().any():
        raise ValueError("行情 close 不得为空")
    with get_duckdb(path=path, read_only=False) as con:
        con.execute("BEGIN")
        try:
            con.execute(PRICES_DDL)
            con.register("_prices", data)
            # DuckDB 的 INSERT OR REPLACE 只覆盖源里出现的列, 表上多出的列会保留旧值。
            # 这里显式先删后插, 保证命中的 (ticker,date) 整行替换, 和新插入的行一致。
            con.execute(
                "DELETE FROM prices USING _prices p "
                "WHERE prices.ticker=p.ticker AND prices.date=p.date"
            )
            con.execute("INSERT INTO prices BY NAME SELECT * FROM _prices")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
