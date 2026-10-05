"""通过普通 Python 变量配置。

首次获取成员不需要本地快照; SEC ZIP 需预先下载到 DATA_DIR。
"""

from pathlib import Path

from quanttoolskit.data import (
    SP500Data,
    load_fundamentals_pit,
    prepare_members,
)

DATA_DIR = Path("data")
DB = DATA_DIR / "sp500.db"
WRITE = False


def main():
    universe = prepare_members()
    # 要复用成员快照，可保存 universe.to_parquet(
    #     DATA_DIR / "sp500_members.parquet", index=False)，
    # 下次使用 load_members(DATA_DIR / "sp500_members.parquet")，无需再联网。
    data = SP500Data(
        universe=universe,
        companyfacts=DATA_DIR / "companyfacts.zip",
        db=DB,
        write=WRITE,
    )
    members = data.members()  # WRITE=True 时同时准备数据库的当前成员表。
    print("members:", len(members))
    facts = data.fundamentals()
    print(facts.shape, data.report)
    # 行情获取使用同一 universe：data.prices('2016-01-01', '2026-10-01')。
    if WRITE:
        snapshot = load_fundamentals_pit(
            db=DB,
            as_of="2025-06-30",
            tickers=["AAPL", "MSFT"],
            fields=["revenue", "net_income"],
        )
        print(snapshot)


if __name__ == "__main__":
    main()
