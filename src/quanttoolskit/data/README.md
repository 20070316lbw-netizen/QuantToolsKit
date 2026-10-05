# data：数据获取、存储与查询

[返回项目首页](../../../README.md)

## 阅读导航

本页介绍数据准备、获取与入库。数据已经入库后，查看
[详细调用指南](USAGE.md)：接口选择、参数含义、整个 SP500 的 panel + TTM 查询、
结果合并及缺失数据检查。

- 首次使用：从下方「SEC 压缩包下载」和「快速开始」开始。
- 已有数据库：[整个 SP500 的 panel + TTM 示例](USAGE.md#整个-sp500同时使用-panel--ttm)。
- 不确定用哪个函数：[读取接口怎么选](USAGE.md#读取接口怎么选)。

- [SEC 压缩包下载](#sec-压缩包下载)
- [快速开始](#快速开始)
- [成员快照](#成员快照)
- [获取与写入](#获取与写入)
- [数据库查询](#数据库查询)
- [日志](#日志)
- [当前范围](#当前范围)
- [实现布局](#实现布局)
- [验证记录](#验证记录)

`data` 现在统一提供成员准备、行情/基本面获取、可选入库以及数据库读取。
不依赖独立的 `sources` / `liudb` 包，也没有命令行注册入口。

## SEC 压缩包下载

下面的完整流程需要先将 [SEC companyfacts ZIP](https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip)
下载到 `data/companyfacts.zip`。已有文件可直接配置其路径，无需再次下载。
只准备成员或获取行情时可以省略 `companyfacts`，也不需要该 ZIP。

仓库提供 [scripts/download_sec.sh](../../../scripts/download_sec.sh)，只需系统自带的 `curl`、
`unzip`。在工具箱仓库目录执行，将身份信息换成你的姓名和邮箱：

```bash
EDGAR_IDENTITY="你的姓名 你的邮箱" sh scripts/download_sec.sh
```

默认下载到**执行命令的当前目录**下的 `data/companyfacts.zip`。也可把脚本用于
消费项目，例如在 `chores` 目录执行：

```bash
EDGAR_IDENTITY="你的姓名 你的邮箱" sh ../QuantToolsKit/scripts/download_sec.sh
```

脚本支持重试及 `.part` 断点续传；下载后核验 ZIP 全部条目的 CRC，通过后才替换
正式文件。失败时保留旧 ZIP，再次运行会续传 `.part`；如果 ZIP 校验失败，按提示
删除 `.part` 后重新下载。已有完整文件时再次运行会下载新快照。
自定义保存目录可设置 `SEC_DATA_DIR="/你的数据目录"`；不需要 Python 环境，也没有包 CLI。

## 快速开始

```python
from quanttoolskit.data import SP500Data, prepare_members

universe = prepare_members()  # 从 Wikipedia 获取当前成员，已包含 CIK
data = SP500Data(
    universe=universe,
    companyfacts="data/companyfacts.zip",
    db="data/sp500.db",
    write=True,
)

members = data.members()  # 按 write 设置保存当前完整成员快照
facts = data.fundamentals()  # 全 universe、全部标准字段、全部历史版本
prices = data.prices("2016-01-01", "2026-10-01")
print(data.report)  # 最近一次获取的行数、缺数据情况、是否写入
```

## 成员快照

首次使用不需要先准备成员 Parquet 或 SEC ticker JSON。`prepare_members()` 会联网
获取 Wikipedia 当前名单，直接使用其 CIK；需要额外核对时才提供可选的
`sec_tickers="data/company_tickers.json"`。该参数只读取本地 JSON，不下载它。

要保存并复用成员快照，可显式操作：

```python
from pathlib import Path
from quanttoolskit.data import load_members

snapshot_path = Path("data/sp500_members.parquet")
snapshot_path.parent.mkdir(parents=True, exist_ok=True)
universe.to_parquet(snapshot_path, index=False)

# 下次读取已有快照，不联网，也不要求 SEC JSON；同样支持 CSV。
universe = load_members(snapshot_path)
```

`load_members` 读取的是保存时的名单；需要更新名单时重新调用 `prepare_members()`。
读取已有库的成员表则使用 `load_constituents(db=...)`。SEC ZIP 仍需要预先下载，
它与成员快照的获取是独立的步骤。

## 获取与写入

实例固定一份 universe，所有方法共享相同证券代码。构造时不联网、不连接数据库。
`write=False` 只返回 DataFrame；`write=True` 在验证后写库并返回同样的结果。
每个方法可用 `write=False/True` 覆盖实例默认值。公司 CIK 不影响行情获取：
未映射 CIK 的证券仍在 universe 中，基本面会明确报告缺映射。
`companyfacts` 可省略以仅使用行情和成员方法，调用基本面时必须指定。
自建 universe 至少包含 `ticker`、`name`；`cik` 列可省略。开启写入后会自动创建
数据库父目录；仅构造对象或 `write=False` 不创建目录和数据库。

基本面获取没有 `fields` 或 `tickers` 参数，默认包含当前定义的 25 个标准字段；
这不等于 SEC 的所有 XBRL 科目。完整原始来源保留在本地 ZIP，获取过程不下载 SEC 数据。
日期异常、无效值进入 `data.quarantine` 并在写库时保存到 `fundamentals_quarantine`。
仅金额类字段推导单季，EPS/加权股数不相减。`filed`、`accn` 等申报身份始终保留。

缺映射/缺 CIK 文件默认报错且不写入。显式 `allow_partial=True` 时，缺来源的整个
证券被跳过，不覆盖其旧数据。成功读取的证券会替换全部标准字段历史；没有命中的
科目会记录到 `missing_fields`，不会保留上次导入的过期值。其他证券、未管理字段和
行情表不受影响。成员快照写入是独立操作，不删除退出成员的行情/基本面历史。

行情通过 yfinance 获取日线，日期范围 `[start, end)`，不自动复权，保留 `close`
和 `adj_close`。部分证券缺行情会报告到 `missing_tickers`；写入按 `(ticker,date)`
更新，未返回的日期和证券保留旧值。查询 `load_prices` 的日期范围则含两端。
数据源没有提供复权价时，`adj_close` 保留空值，不用未复权收盘价填充。

## 数据库查询

完整调用与结果处理见 [详细调用指南](USAGE.md)，下面只展示最小查询。

字段筛选和 PIT/TTM 在数据库读取时进行：

```python
from quanttoolskit.data import load_fundamentals_pit, load_fundamentals_ttm, load_prices

snapshot = load_fundamentals_pit(
    db="data/sp500.db",
    as_of="2025-06-30",
    tickers=["AAPL", "MSFT"],
    fields=["revenue", "net_income"],
)
ttm = load_fundamentals_ttm(
    db="data/sp500.db",
    dates=["2025-06-30"],
    fields=["revenue", "net_income"],
)
prices = load_prices(db="data/sp500.db", tickers="AAPL", start="2025-01-01")
```

另导出 `load_constituents`、`load_fundamentals`、`load_fundamentals_panel`、
`load_latest_filed`。查询错误、数据库缺失或表结构不兼容会明确抛错，不伪装成空结果。
所有读取接口显式传入 `db`；获取和查询都统一 ticker 大写及短横线写法。
PIT 的时间精度是申报日，盘中使用需另核验发布时间；TTM 仅允许可加金额字段，
同时检查四个季度的总跨度和各相邻季度间隔。

## 日志

包内日志走 loguru，默认对本包关闭，避免污染使用方的 stderr。排查问题时在 import
之后执行 `logger.enable("quanttoolskit")` 重新打开。

## 当前范围

本阶段使用当前成员快照；历史成员资格区间、完整 ticker 改名/前身关系维护尚未迁入。
已登记的前身 CIK 为 Google、Disney、ExxonMobil，不保证覆盖所有重组。
SYF/TFC 收入口径缺口仍保留，未自动合成银行收入。

## 实现布局

```text
src/quanttoolskit/data/
├── README.md                # 准备、获取与入库入口
├── USAGE.md                 # 详细调用与 SP500 查询示例
├── sp500.py                 # SP500Data
├── universe.py              # 成员准备与 CIK 映射
├── connection.py
├── schema.py
├── writer.py                # 事务写入
├── preprocessing.py         # 现有预处理功能
├── sources/
│   ├── wikipedia.py
│   ├── yahoo.py
│   └── sec/
│       ├── bulk.py
│       ├── fields.py
│       └── normalize.py
└── readers/
    ├── constituents.py
    ├── prices.py
    └── fundamentals.py
```

[examples/sp500_data.py](../../../examples/sp500_data.py) 是普通 Python 脚本，配置直接写成变量。
开发时可以在消费项目中使用 `uv add --editable ../QuantToolsKit`，本地改动立即生效。
`chores` 已切换到该本地可编辑依赖，示例是 `chores/use_toolkit.py`。

## 验证记录

实际 SEC ZIP 的迁移验证：503 只、2,258,207 行，写入临时数据库后与此前实验库
逐行对照差异为 0；2016/2020/2025 三个时点的 PIT 和 AAPL TTM 查询通过。
原有大库只用于只读比较。49 条原始异常在推导前隔离；旧实验库另有 1 条从异常
累计值推导出的异常季度，新流程不再生成它。

本目录的测试为 [tests/test_market_data.py](../../../tests/test_market_data.py)、
[tests/test_preprocessing.py](../../../tests/test_preprocessing.py)和
[tests/test_transfer_data.py](../../../tests/test_transfer_data.py)，
覆盖成员准备、SEC 归一化、事务写入、schema 契约、数据库读取、预处理和行情 MultiIndex DataFrame 转换。

仓库级的 Ruff、格式检查、锁文件同步和构建校验由根目录 CI 负责，本页只记录本目录的验证。
实网验证 `prepare_members()` 返回 503 只且无缺失 CIK；同一入口获取 AAPL/MSFT
四个交易日共 8 行行情，复权价齐全。
完整验证脚本在 `chores/validate_toolkit.py`，统计保存到
`chores/data/toolkit_closeout_report.json`；脚本用实验成员快照对照，避免实时名单变化干扰比较。

## 读取后统一数据结构

量化计算统一使用 `[date, ticker]` MultiIndex DataFrame，规则见
[项目约定](../../../docs/data-structure.md)。行情读取示例：

```python
from quanttoolskit.data import load_prices, to_date_ticker_frame

prices = to_date_ticker_frame(df=load_prices(db="data/sp500.db"))
# date/ticker 为索引，其余行情列保留，可直接传入收益率和波动率函数。
```

`to_date_ticker_frame(df=...)` 是通用转换入口；`validate_prices` 只接受已转换的
DataFrame，校验指定价格列（默认 close），保留索引顺序与数据列，不转换索引。
两者都不修改输入；收益率和波动率内部调用 `validate_prices`，一般只需显式转换索引。
`set_datetime_index` 也返回双层索引，要求提供 ticker。
基本面原始版本表须先筛选和透视，不能直接丢弃字段、期间或版本维度。
