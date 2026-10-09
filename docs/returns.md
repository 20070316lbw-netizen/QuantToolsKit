# returns：收益率

[返回项目首页](../README.md) · [波动率](volatility.md)

实现位于 [returns.py](../src/quanttoolskit/returns.py)。

逐证券收益率输入为含价格列(默认 `adj_close`)的 `[date, ticker]` MultiIndex DataFrame。
输出为同索引的 Series, `Series.name` 为指标名。计算前重新排序, 输入顺序不影响结果。
`build_nav` 接收已聚合的单一组合逐日简单收益率 Series, 返回逐日净值。
结构与读取边界见 [项目数据结构约定](data-structure.md)。

## 使用示例

```python
from quanttoolskit import future_returns, historical_return, log_returns
from quanttoolskit.data import load_prices, to_date_ticker_frame

prices = to_date_ticker_frame(df=load_prices(db="data/sp500.db"))

# 截至当天的历史表现, 可用于动量或反转特征。
momentum = historical_return(df=prices, n_periods=21)

# 未来收益标签, 只在事后生成。
label = future_returns(df=prices, n_periods=5, gap=1)

# 单期对数收益, 可用于累计对数动量。
daily_log = log_returns(df=prices)
```

## 参数与计算口径

| 函数 | 参数默认值 | 公式 | Series.name |
| --- | --- | --- | --- |
| `historical_return` | `n_periods=5, price_col="adj_close"` | `price[t] / price[t - n_periods] - 1` | `historical_return_{n_periods}` |
| `future_returns` | `n_periods=5, gap=1, price_col="adj_close"` | `price[t + gap + n_periods] / price[t + gap] - 1` | `forward_return_{n_periods}_gap_{gap}` |
| `log_returns` | `price_col="adj_close"` | `log(price[t]) - log(price[t - 1])` | `log_return` |

`n_periods` 必须是大于零的整数, `gap` 必须是非负整数;布尔值不接受。
默认未来标签在下一条交易记录的收盘价入场, 持有 5 期后出场。

## 缺失值与使用限制

- 期数按每只股票自己的交易记录计数, 不跨股票取值, 不自动补齐交易日。
- `log_returns` 返回对数收益, 每只股票首行或相邻任一价格缺失时为 NaN;
  [动量因子](momentum.md) 累计这类单期收益。
- 多期累计对数收益使用 `quanttoolskit.factors.cumulative_log_returns`,
  如 `cumulative_log_returns(prices, window=63, skip=0)`;目前与动量共用接口。
  window=1、skip=0 时数值与 log_returns 相同, 但输出名称不同。
  详见 [累计对数收益与动量](momentum.md), 窗口内部缺失会导致 NaN。
- 简单收益率以小数表示;历史或未来记录不足、端点价格缺失时为 NaN, 不填补价格。
- 重复键、缺失日期或 ticker、非正价格会明确报错;价格校验由内部
  `validate_prices` 完成。长表必须先用 `to_date_ticker_frame` 转换。
- `future_returns` 使用未来数据, 只用于事后生成标签或评估预测, 不能进入特征。

验证见 [test_returns.py](../tests/test_returns.py)、
[test_momentum.py](../tests/test_momentum.py) 和
[test_dataframe_contract.py](../tests/test_dataframe_contract.py)。

## 返回类型迁移

单结果现返回 Series, 使用 `result.name` 查看指标名,
用 `result.loc[(date, ticker)]` 取标量, 无需再选择指标列。
附加到行情使用 `prices.join(result)`, 作为后续 DataFrame 输入使用 `result.to_frame()`。
多指标合并使用 `pd.concat([result_a, result_b], axis=1)`;计算公式和缺失值口径不变。

## 逐日组合收益转净值

```python
import pandas as pd
from quanttoolskit.returns import build_nav

daily_returns = pd.Series(
    [0.0, 0.1, -0.05],
    index=pd.date_range("2024-01-01", periods=3, name="date"),
)
nav = build_nav(daily_returns, initial_capital=100.0)
assert nav.round(2).tolist() == [100.0, 110.0, 104.5]
assert nav.name == "nav"
```

- 输入是单一组合的实数简单收益率, 用小数表示, 不能直接传入对数收益。
  多证券收益须由调用方按自己的仓位与缺失报价规则聚合, 本函数不生成权重。
- 日期索引必须是 DatetimeIndex, 日期键非空且唯一。计算按日期排序,
  输出索引名为 `date`, 保留日期、时区和精度, 不补齐交易日或修改输入。
- `initial_capital` 默认 1.0, 必须为有限正实数, 不接受布尔值。
  公式为 `initial_capital * prod(1 + r)`; 首行包含首日收益,
  不自动添加期初净值。以首日建仓为起点时, 调用方须明确将首日收益定义为 0。
- 遇到 NaN 后, 当日及之后净值都为 NaN, 因为收益链已不完整;
  不会跳过缺失收益继续累乘。空输入返回 float64 空 Series。
- 收益为 -1 时净值归零; 小于 -1 时按公式产生负净值,
  本函数不模拟杠杆强平或追加资金, 也不单独扣除费用。
- 非 Series 或非实数期初资金报 TypeError; 无效日期索引、无穷收益、
  非实数数值收益或非正/非有限期初资金报 ValueError。

与 [调仓日历](rebalance.md) 共用的可运行示范见
[rebalance_nav.py](../examples/rebalance_nav.py), 运行
`python examples/rebalance_nav.py`。验证见
[test_build_nav.py](../tests/test_build_nav.py) 和
[test_rebalance_nav_example.py](../tests/test_rebalance_nav_example.py)。
