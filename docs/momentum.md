# factors：累计对数收益与动量因子

[返回项目首页](../README.md) · [收益率](returns.md) · [反转因子](reversal.md)

实现位于 [momfactor](../src/quanttoolskit/factors/momfactor/)。

输入为 `[date, ticker]` MultiIndex DataFrame, 默认价格列为 `adj_close`。
输出为同索引的 Series, `Series.name` 为指标名。计算前重新排序, 输入顺序
不影响结果。结构与读取边界见 [项目数据结构约定](data-structure.md)。

## 使用示例

```python
import pandas as pd

from quanttoolskit.data import load_prices, to_date_ticker_frame
from quanttoolskit.factors import cumulative_log_returns, momentum_12_1

prices = to_date_ticker_frame(df=load_prices(db="data/sp500.db"))

# 过去 63 期累计对数收益率, 跳过最近 5 期；也可作为动量特征。
custom = cumulative_log_returns(df=prices, window=63, skip=5)

# 经典 12-1 动量, 每个月近似为 21 条交易记录。
classic = momentum_12_1(df=prices)
features = pd.concat([custom, classic], axis=1)
```

也可从 `quanttoolskit.factors.momfactor` 导入这两个接口。
自包含的 [可运行示范](../examples/return_factors.py) 展示累计收益、反转、
横截面标准化和分桶, 不依赖本地数据库。

`cumulative_log_returns` 既能计算窗口累计对数收益率, 也能构造动量特征,
目前共用 factors 下的同一接口。window=1、skip=0 时数值与
`quanttoolskit.log_returns` 相同；函数使用滚动窗口, 不从序列首日累计。

## 参数与计算口径

| 函数 | 参数默认值 | 完整窗口公式 | Series.name |
| --- | --- | --- | --- |
| `cumulative_log_returns` | `window` 必填, `skip=0, price_col="adj_close"` | `sum(r[t-skip-window+1 : t-skip+1])` | `cumulative_log_return_{window}_skip_{skip}` |
| `momentum`（旧接口） | 参数与上述接口相同 | 与上述接口相同 | `momentum_{window}_skip_{skip}` |
| `momentum_12_1` | `trading_days_per_month=21, price_col="adj_close"` | `log(price[t-m]) - log(price[t-12*m])`, `m` 为每月记录数 | `mom_12_1` |

`r[t] = log(price[t]) - log(price[t-1])`, 上述切片右端不包含。
完整窗口内价格均有效时, 通用动量等于
`log(price[t-skip]) - log(price[t-skip-window])`。
实现累计窗口内的单期对数收益, 窗口内部缺失不会被端点公式忽略。

`window` 和 `trading_days_per_month` 必须是正整数, `skip` 必须是非负整数；
布尔值不接受。12-1 使用 **11 个月收益窗口、跳过最近 1 个月**, 默认
`window=231, skip=21`, 首次有效值需要 253 条价格记录。
使用 12 个月窗口再跳过 1 个月会覆盖第 13 至第 1 个月, 不是这里的 12-1 口径。

## 缺失值与使用限制

- 月份用固定交易记录数近似, 不按日历月重采样。期数按每只股票自己的记录
  计数, 停牌或缺少交易日时不自动补齐, 也不跨股票滚动或位移。
- 每只股票前 `window + skip` 条记录为 NaN；窗口内任一价格缺失时为 NaN,
  即使起点与终点价格有效。缺失价格离开窗口后恢复计算。
- 跳过区间内的价格不参与对应日期的因子计算；因子使用当天或更早的数据。
- 值为累计对数收益, 转换为简单累计收益可用 `numpy.expm1`, 不是百分数。
- 价格结构与所选列由 `validate_prices` 校验；长表必须先转换, 重复键、
  缺失键、非正价格会报错。不会修改输入, 空输入保留 Series.name 和标准索引。
- 默认使用复权价格；若明确需要原始收盘价, 可传 `price_col="close"`。
  `mom_12_1` 名称不包含每月记录数, 比较多种月份近似时应先重命名 Series。

验证见 [test_cumulative_log_returns.py](../tests/test_cumulative_log_returns.py)、
[test_momentum.py](../tests/test_momentum.py) 和
[test_dataframe_contract.py](../tests/test_dataframe_contract.py)。

## 返回类型迁移

`cumulative_log_returns`、`momentum`、`momentum_12_1` 直接返回 Series。
用 `result.loc[(date, ticker)]` 取标量, 将结果附加到行情可用 `prices.join(result)`。
累计对数收益、窗口长度和 skip 的定义不变。

## 函数名称迁移

新代码用 `cumulative_log_returns` 替代通用 `momentum`, 输出名称随之更明确：

```python
# 原调用仍可用, 输出名为 momentum_63_skip_5。
from quanttoolskit.factors import momentum

old = momentum(prices, window=63, skip=5)

# 新调用数值相同, 输出名为 cumulative_log_return_63_skip_5。
new = cumulative_log_returns(prices, window=63, skip=5)
```

依赖旧 Series.name 的代码可继续调用 `momentum`, 或在新结果上显式 rename。
`momentum_12_1` 的函数名、默认参数和 `mom_12_1` 输出名保持不变。
