# Qlib 社区行情

2026-10-09 已实现。流程只包含下载、读取转换、保存三个步骤。

在仓库目录安装可选依赖：`uv sync --extra qlib`。
未安装时仍可使用其余数据功能, 只有读取 Qlib 时要求 pyqlib。

## 1. 下载并保留原始文件

[下载脚本](../scripts/download_qlib.sh) 沿用 demo 的下载与校验流程。
默认保存到运行目录下的 `data/qlib-community/<发布版本>/`。

```bash
sh scripts/download_qlib.sh --check-only
sh scripts/download_qlib.sh --tag 2026-10-07
# 中断后继续同一个发布版本：
sh scripts/download_qlib.sh --tag 2026-10-07 --resume
```

省略 --tag 时解析 latest, manifest 和压缩包来自同一个具体发布。
`--dest` 指定保存目录, `--download-only` 仅下载不解压。
脚本优先使用仓库的 .venv/bin/python；也可通过 QLIB_PYTHON 指定解释器。

```text
data/
├── qlib-community/2026-10-07/
│   ├── qlib_bin.tar.gz
│   ├── qlib_bin.manifest.json
│   └── cn_data/               # 原样解压的 Qlib 数据
└── qlib_cn.duckdb             # 用于查询的行情库
```

原始压缩包和 manifest 就是快照, 按版本保留, 不再建立快照登记表。
保留同发布下载、大小与 SHA256 校验、安全解压、已有目录保护及续传。
发布版本与行情截止日分别使用 manifest 的 release_tag 与 target_trade_date。

## 2. 读取并转换

[read_qlib_prices](../src/quanttoolskit/data/sources/qlib.py) 从本地文件读取：

```python
read_qlib_prices(*, data_dir, start, end, tickers=None, market=None)
```

- tickers 与 market 二选一, 历史股票池筛选直接交给 Qlib。
- 全部保留社区包提供的复权后数据及可用日频字段, 保留来源字段名和数值。
- 不限定六列, 也不另算复权价。源包提供的 adjclose、amount、change、vwap 等一并保留。
- 日期范围含两端, 缺失值保留, 不补报价或额外补齐日期。
- 将 datetime/instrument 改为 date/ticker, 去掉字段前缀 $, 最后必须经过
  `to_date_ticker_frame`, 返回有序、键非空且唯一的 `[date, ticker]` DataFrame。

直接在调用时初始化指定的 Qlib provider, 第一版不增加独立进程管理。
同一进程暂不并发读取不同 provider。pyqlib 延迟导入, 作为可选依赖安装。

## 3. 保存与查询

只新增一张 `qlib_prices` 表：

| 内容 | 约定 |
| --- | --- |
| 主键 | `(date, ticker)` |
| 行情列 | 源包实际提供的全部日频字段, 保留缺失值与数值精度 |
| 来源列 | `release_tag`, 普通列, 标明当前数据来自哪个发布 |

保存只提供一个函数：

```python
save_qlib_prices(*, db, prices, release_tag)  # 保存标准 DataFrame
```

**每次保存都在事务内整表替换 qlib_prices**, 包括按本次源字段重建列结构。
保存范围就是传入的 prices, 不做增量追加或跨版本合并。
写入失败回滚并保留旧表；空数据拒绝写入。
这也意味着只传入两只股票的行情, 库里就只保存这两只股票。
release_tag 使用下载目录对应的具体发布标签, 不使用 latest 作为持久化身份。

数据库只保存当前选定数据, 历史原始文件继续保留。
查询由调用方手写 SQL, 不增加专用查询函数或 reader。
查询结果需要进入计算时, 去掉来源列 release_tag 并经过 `to_date_ticker_frame`。
历史市场筛选在源文件读取时完成, 第一版不把成分区间另建表入库。
原有 Yahoo 的 prices 表继续使用, Qlib 不写入该表。

## 调用示例

日期范围含两端, 以下示例只保存所选两只证券：

```python
from pathlib import Path

from quanttoolskit.data import (
    get_duckdb,
    read_qlib_prices,
    save_qlib_prices,
    to_date_ticker_frame,
)

prices = read_qlib_prices(
    data_dir="data/qlib-community/2026-10-07/cn_data",
    start="2024-01-01",
    end="2024-12-31",
    tickers=["SH600000", "SZ000001"],
)
save_qlib_prices(db="data/qlib_cn.duckdb", prices=prices, release_tag="2026-10-07")

with get_duckdb(path=Path("data/qlib_cn.duckdb")) as con:
    raw = con.execute(
        "SELECT * EXCLUDE (release_tag) FROM qlib_prices "
        "WHERE ticker = ? ORDER BY date, ticker",
        ["SH600000"],
    ).df()
stored = to_date_ticker_frame(df=raw)
```

[完整可运行示例](../examples/qlib_community_data.py) 默认使用临时数据库,
读出全部字段后保存、手写 SQL 查询并逐值验证往返：

```bash
.venv/bin/python examples/qlib_community_data.py \
  --data-dir data/qlib-community/2026-10-07/cn_data
```

需要保留数据库时加 `--db data/qlib_cn.duckdb`。
可以用 `--market csi300` 替代默认两只证券, 或指定 `--tickers SH600000 SZ000001`。
`--start`、`--end` 默认 2024-01-01 和 2024-12-31。

## 范围与验证

复用现有 data 模块的连接、schema 和 writer,
提供 read_qlib_prices、save_qlib_prices 两个函数。
不增加数据对象类、快照登记、导入日志、覆盖追踪、成分区间表、批次调度或独立工作进程。
全市场或长区间的读取与内存优化, 等基础流程可用后再按实际需要处理。

[读取和入库测试](../tests/test_qlib_data.py) 覆盖全部字段、标准索引、缺失值、
历史股票池、空查询、精度往返、重复键拒绝、整表替换及失败回滚。
[下载测试](../tests/test_qlib_download.py) 使用本地模拟发布验证校验、保护及续传,
不需要下载真实大包。安装可选依赖后还会运行真实 Qlib 二进制读取和示例测试。

2026-10-09 本地实包验证使用发布 2026-10-07：
SH600000、SZ000001 在 2024 年共 484 行、10 个字段, 全部值与原始二进制一致,
其中六个基础字段与 demo 的原有导出一致。
csi300 在 2024-01-02 至 2024-01-05 共 1,200 行、10 个字段,
写入临时数据库后全部字段往返一致, 主键确认是 `(date, ticker)`。
以上不覆盖全市场长区间的内存压力验证。

```bash
.venv/bin/python -m pytest tests/test_qlib_data.py tests/test_qlib_download.py -q
```

计算接口已另行迁移为单结果 Series、多结果 DataFrame；Qlib 读取仍返回标准 DataFrame。

[数据模块](../src/quanttoolskit/data/README.md) · [数据契约](data-structure.md)
