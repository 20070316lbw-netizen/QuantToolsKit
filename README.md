# QuantToolsKit

[![CI](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml/badge.svg)](https://github.com/20070316lbw-netizen/QuantToolsKit/actions/workflows/ci.yml)

个人量化工具箱。各模块的使用说明放在对应目录，点击下面的模块名查看；包根下的两个
通用模块见[收益与波动率](#收益与波动率)。

## 模块目录

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| [data](src/quanttoolskit/data/README.md) | 成员准备、SEC 压缩包下载、行情与基本面获取、DuckDB 入库及查询 | 已实现 |
| [returns](#收益与波动率) | 简单收益率：历史收益特征与未来收益标签 | 已实现 |
| [volatility](#收益与波动率) | 滚动波动率：历史波动特征与未来波动标签 | 已实现 |
| [indicators](src/quanttoolskit/indicators/README.md) | 技术指标 | 占位 |
| [factors](src/quanttoolskit/factors/README.md) | 因子计算 | 占位 |
| [portfolio](src/quanttoolskit/portfolio/README.md) | 权重、调仓与组合操作 | 占位 |
| [performance](src/quanttoolskit/performance/README.md) | 收益、回撤与绩效统计 | 占位 |
| [plotting](src/quanttoolskit/plotting/README.md) | 绘图 | 占位 |

```text
src/quanttoolskit/
├── data/          # 数据获取、存储、查询、预处理
├── indicators/    # 技术指标
├── factors/       # 因子计算
├── portfolio/     # 权重、调仓、组合操作
├── performance/   # 收益、回撤、绩效统计
├── plotting/      # 绘图
├── returns.py     # 简单收益率：历史收益特征与未来收益标签
└── volatility.py  # 滚动波动率：历史波动特征与未来波动标签
```

## 安装

开发时在消费项目（如 `chores`）里安装本地可编辑依赖，修改工具箱后直接生效：

```bash
uv add --editable ../QuantToolsKit
```

仓库版本的安装方式：

```bash
uv add "quanttoolskit @ git+https://github.com/20070316lbw-netizen/QuantToolsKit.git"
```

安装后从 [data 使用说明](src/quanttoolskit/data/README.md#快速开始) 开始；价格特征
与标签见[收益与波动率](#收益与波动率)。

## 收益与波动率

`returns` 和 `volatility` 是包根下的两个通用模块，输入都是 prices 长表（至少含
`date`、`ticker` 和价格列），输出统一为以 `[date, ticker]` 为索引的 Series，
算不出的位置为 NaN。计算前会按股票、日期重新排序，入参顺序不影响结果。

```python
from quanttoolskit import (
    forward_volatility,
    future_returns,
    historical_return,
    history_vol,
)

# 历史特征：截至当天的表现，可用于动量、反转、波动率因子
momentum = historical_return(df=prices, n_periods=21)
vol = history_vol(df=prices, window=21)

# 未来标签：只在事后生成 y，不能进入特征
label = future_returns(df=prices, n_periods=5, gap=1)
forward_risk = forward_volatility(df=prices, window=21, gap=1)
```

四个函数的口径：

- `historical_return`：`price[t] / price[t - n_periods] - 1`。
- `history_vol`：最近 `window` 个日收益率的样本标准差（`ddof=1`），不年化。
- `future_returns`：`price[t + gap + n_periods] / price[t + gap] - 1`，默认
  `gap=1` 在下一条交易记录进场、持有 5 期出场。
- `forward_volatility`：`std(r[t + gap + 1] ... r[t + gap + window])`，等价于用
  `price[t + gap]` 起 `window + 1` 个价格算出的 `window` 个收益率。

需要注意：

- 期数按每只股票自己的交易记录计数，不跨股票取值；价格缺失不填补，窗口内含缺失
  收益率时结果为 NaN。
- 重复的 `(date, ticker)`、日期或 ticker 缺失、非正价格都会明确报错，不静默丢弃。
- `n_periods`、`window` 必须是整数（`window >= 2`，`n_periods >= 1`），`gap >= 0`。
- `future_returns` 和 `forward_volatility` 使用未来数据，只能用于事后生成标签或
  评估预测，不能当作特征。

两个模块共用的长表归一化函数 `transfer_prices` 从 `quanttoolskit.data` 导出。

## 许可证

本项目采用 [MIT License](LICENSE)。
