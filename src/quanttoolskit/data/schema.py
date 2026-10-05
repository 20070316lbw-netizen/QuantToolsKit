"""数据包管理的 DuckDB 表结构及成员列契约。

constituents 是当前证券快照，ticker 是主键；多个股类可以共享 CIK。
fundamentals 保留每份文件的版本，不能只以 ticker/period_end 去重。
prices 以 ticker/date 为主键，每个证券每天一行。

这些常量只声明 SQL，不在导入模块时创建数据库。writer 在写入事务内执行它们。
"""

CONSTITUENTS_COLUMNS = (
    "ticker",
    "name",
    "sector",
    "sub_industry",
    "date_added",
    "cik",
    "sec_cik",
    "sec_title",
)

# 当前成员是完整快照；替换及插入由同一个事务保护。
CONSTITUENTS_DDL = """
    CREATE OR REPLACE TABLE constituents (
        ticker VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        sector VARCHAR,
        sub_industry VARCHAR,
        date_added DATE,
        cik VARCHAR,
        sec_cik VARCHAR,
        sec_title VARCHAR
    )
    """

# filed 是可用时间，accn 是申报版本；同一报告期间的重述与比较期申报分别保存。
# period_months=0 为时点；3/6/9/12 为期间。fundamentals_quarantine 复用相同列结构。
DDL = """
    CREATE TABLE IF NOT EXISTS fundamentals (
        ticker VARCHAR NOT NULL,
        cik VARCHAR,
        field VARCHAR NOT NULL,
        concept VARCHAR,
        unit VARCHAR,
        period_start DATE,
        period_end DATE NOT NULL,
        period_months INTEGER NOT NULL,
        value DOUBLE,
        fy INTEGER,
        fp VARCHAR,
        form VARCHAR,
        accn VARCHAR NOT NULL,
        filed DATE NOT NULL,
        derived BOOLEAN NOT NULL,
    PRIMARY KEY(ticker,field,period_end,period_months,accn))
    """


# close 必须有值，其他行情列允许缺失；不在存储层自动补齐或复权。
PRICES_DDL = """
    CREATE TABLE IF NOT EXISTS prices (
        date DATE NOT NULL,
        ticker VARCHAR NOT NULL,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE NOT NULL,
        adj_close DOUBLE,
        volume DOUBLE,
    PRIMARY KEY(ticker,date))
    """
