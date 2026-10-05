# data：详细调用指南

[返回 data 使用说明](README.md) · [返回项目首页](../../../README.md)

本页面向已经准备好 DuckDB 数据库的调用方。首次下载 SEC ZIP、准备成员与入库，
见 [README 快速开始](README.md#快速开始)。所有示例使用公开入口 `quanttoolskit.data`。
示例中的相对路径以执行 Python 时的工作目录为准。

- [读取接口怎么选](#读取接口怎么选)
- [日期、期间与版本](#日期期间与版本)
- [整个 SP500：同时使用 panel + TTM](#整个-sp500同时使用-panel--ttm)
- [查一个时点或核对历史版本](#查一个时点或核对历史版本)
- [参数与缺失结果](#参数与缺失结果)
- [其他入口](#其他入口)

## 读取接口怎么选

| 需求 | 接口 | 返回粒度 |
| --- | --- | --- |
| 核对原始申报与重述 | `load_fundamentals` | 原始版本行，同一期可有多行 |
| 查某一天可见的基本面 | `load_fundamentals_pit` | 默认每个股票、字段、期间长度取最近一期 |
| 在多个调仓日取最近一期 | `load_fundamentals_panel` | 每个日期、股票、字段、期间长度一行 |
| 在多个调仓日取滚动一年金额 | `load_fundamentals_ttm` | 每个日期、股票、字段一行 |
| 检查库中最近申报日 | `load_latest_filed` | 每个股票一行，不是历史 PIT 查询 |

`panel` 和 `ttm` 都支持多个日期，也都按当时可见的版本查询。
区别是 `panel` 选择一期，`ttm` 合计最近四个单季。
`panel` 不局限于资产负债表：也可以用 `period_months=3` 取单季金额，或用 `12` 取年度金额。

## 日期、期间与版本

- `date` / `as_of`：查询时点，回测中通常是调仓日。
- `period_end`：财务数据所属期间的截止日。
- `filed`：申报日期。PIT、panel、TTM 只使用 `filed <= 查询时点` 的版本。
- `period_months`：`0` 表示时点余额；`3/6/9/12` 表示单季、半年、九个月、全年期间。

例如第一季度于 3 月 31 日结束、5 月 1 日申报，4 月调仓时不能使用它。
后续重述也只在其申报之后可见；同一期选择当时最新申报版本，申报日相同时优先直接报告值，
再按文件号排序。接口的 PIT 精度只有日期，盘中使用需要另核验公开时刻。

TTM（最近十二个月）将最近四个单季金额相加，随着新季度公布滚动更新。
它不同于 `period_months=12` 的报告值：第二季度公布后，TTM 可以包含今年上半年和去年下半年。
半年、九个月累计值不能直接与包含在其中的单季相加；入库流程会为可加金额推导单季，
TTM 读取的始终是 `period_months=3`。

## 整个 SP500：同时使用 panel + TTM

### 前提

数据库需包含 `constituents` 成员表与 `fundamentals` 基本面表。首次准备时使用：

```python
from quanttoolskit.data import SP500Data, prepare_members

data = SP500Data(
    universe=prepare_members(),
    companyfacts="data/companyfacts.zip",  # 事先下载的本地 SEC ZIP
    db="data/sp500.db",
    write=True,
)
data.members()
data.fundamentals()
print(data.report)  # 检查来源、字段缺失与是否成功写入
```

此步骤会联网获取当前成员并写库；后续查询无需重复导入，也不需要行情表。

### 查询、合并与检查覆盖率

下面完整示例读取已保存的成员名单，在同一组日期上查询最近一期资产、权益与滚动一年金额。
结果转成每个 `(date, ticker)` 一行，并计算一个净利润率示例。

```python
from pathlib import Path

import pandas as pd

from quanttoolskit.data import (
    load_constituents,
    load_fundamentals_panel,
    load_fundamentals_ttm,
)

db = Path("data/sp500.db")
members = load_constituents(db=db)
tickers = members["ticker"].tolist()
dates = pd.to_datetime(["2025-06-30", "2025-09-30", "2025-12-31"])

panel = load_fundamentals_panel(
    dates=dates,
    tickers=tickers,
    fields=["total_assets", "total_equity"],
    period_months=0,
    db=db,
)
ttm = load_fundamentals_ttm(
    dates=dates,
    tickers=tickers,
    fields=["revenue", "net_income", "operating_cash_flow"],
    db=db,
)

# 长表适合检查来源；转宽表后方便按股票计算。
# 明确筛选 period_months=0，因此 panel 的每个 date/ticker/field 唯一。
keys = ["date", "ticker"]
balances = panel.pivot(index=keys, columns="field", values="value")
flows = ttm.pivot(index=keys, columns="field", values="value").add_suffix("_ttm")

# 保留全部日期和成员组合，未返回的数据留为 NaN，避免悄悄丢掉股票。
grid = pd.MultiIndex.from_product([dates, tickers], names=keys)
features = balances.join(flows, how="outer").reindex(grid)
expected = [
    "total_assets",
    "total_equity",
    "revenue_ttm",
    "net_income_ttm",
    "operating_cash_flow_ttm",
]
features = features.reindex(columns=expected)
features.columns.name = None

# 只对营收为正的记录计算净利润率，不把缺失金额补成零。
features["net_margin_ttm"] = features["net_income_ttm"] / features["revenue_ttm"].where(
    features["revenue_ttm"] > 0
)

# 同时保留各字段所属财务期间，以及 panel 的申报日期，供核对。
balance_ends = panel.pivot(index=keys, columns="field", values="period_end")
balance_filed = panel.pivot(index=keys, columns="field", values="filed")
flow_ends = ttm.pivot(index=keys, columns="field", values="period_end")
features = features.join(balance_ends.add_suffix("_period_end"))
features = features.join(balance_filed.add_suffix("_filed"))
features = features.join(flow_ends.add_suffix("_ttm_period_end"))

coverage = features[expected].notna().groupby(level="date").sum()
print("成员数量：", len(tickers))
print("各日期、各字段有效股票数：\n", coverage)
print(features.reset_index().head())
```

无需逐只股票循环。`panel` 和 `ttm` 返回长表，`features` 是合并后的宽表。
TTM 返回的 `period_end` 是四个季度中最新季度的截止日，不含各季度的 `filed`；
需要核对组成季度时，使用下方 `pit(latest_only=False, period_months=3)`。

显式传入成员名单很重要：省略 `tickers` 会查库中所有股票，而更新成员表不会删除退出成员的历史。
这里使用的是**库中保存的固定成员快照**，不会自动刷新为今天的名单，也不会按每个调仓日重建历史名单。
项目尚未维护历史成员资格区间；用当前名单回测过去存在幸存者偏差，财务 PIT 不能解决股票池偏差。

各公司、各字段的最新期间可能不同；按 `date/ticker` 合并并不保证 `period_end` 相同。
例如计算 ROE 时，还需要自行构造合适的平均权益，不能把单个期末权益当成已计算好的平均权益。

## 查一个时点或核对历史版本

```python
from quanttoolskit.data import load_fundamentals, load_fundamentals_pit

# 查询当天已公布的所有单季，每个期间取当时最新版本；可核对 TTM 组成季度。
quarters = load_fundamentals_pit(
    "2025-09-30",
    tickers="AAPL",
    fields="net_income",
    period_months=3,
    latest_only=False,
    db="data/sp500.db",
)

# 查看指定财务期间的原始版本行；filed_until 只过滤，不做版本去重。
versions = load_fundamentals(
    tickers="AAPL",
    fields="net_income",
    start="2024-01-01",
    end="2025-09-30",
    period_months=3,
    filed_until="2025-09-30",
    db="data/sp500.db",
)
```

`load_fundamentals` 的 `start/end` 筛选的是 `period_end`，不是申报日期。
PIT 默认 `latest_only=True`，只保留每个 `(ticker, field, period_months)` 的最近一期。

## 参数与缺失结果

| 参数 | 含义 |
| --- | --- |
| `db` | 所有数据库读取接口都必须显式提供 |
| `tickers` | 单个代码或代码序列；`None` 不限股票，空序列不匹配 |
| `fields` | 标准字段名或序列；拼错会报错。普通基本面读取默认不限字段，TTM 默认选全部可加金额字段 |
| `period_months` | 原始、PIT、panel 可传单个值或序列；TTM 固定读取单季，没有此参数 |
| `dates` | panel/TTM 的查询日期序列；日期去重，结果按日期等键排序 |
| `max_staleness_days` | 用财务截止日距查询日的天数限制陈旧数据；`None` 表示不限 |

陈旧阈值默认：PIT 不限、panel 为 550 天、TTM 为 200 天。
TTM 的阈值针对最近一个单季，并非要求四个季度都在最近 200 天内。

TTM 仅支持可加金额字段，例如 `revenue`、`net_income`、`operating_cash_flow`、`capex`。
资产余额、EPS、股数不能传给 TTM。标准字段及单位定义见
[sources/sec/fields.py](sources/sec/fields.py)。

TTM 要求四季齐全，首尾截止日相差 250–300 天，相邻截止日相差 70–125 天。
未满足条件、字段缺失或数据过旧时，不返回对应行；最近四季不完整时不会退回更早的完整窗口。
不要默认缺失等于零，也不要默认每个日期必定得到全部成员。
来源缺失与字段缺失可查导入时的 `data.report`；查询为空则结合筛选条件、申报日期、
陈旧阈值及四季完整性核查。数据库不存在或表结构异常会明确报错。

## 其他入口

- `prepare_members()`：联网准备当前成员；`load_members(path)`：读取保存的 CSV/Parquet 快照。
- `load_constituents(db=...)`：读取库中成员快照，不联网更新。
- `SP500Data.prices(start, end)`：获取整个 universe 的行情，`end` 不含当天。
- `load_prices(db=..., tickers=..., start=..., end=...)`：读取已入库行情，两端日期都包含。
- `load_latest_filed(db=..., tickers=...)`：查看已入库的最近申报日，辅助判断更新需求，调用本身不会更新数据。

获取与写入选项见 [README](README.md#获取与写入)。查询函数的完整参数及返回列见
[readers/fundamentals.py](readers/fundamentals.py)。
