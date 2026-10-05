# returns：收益率

[返回项目首页](../README.md) · [波动率](volatility.md)

实现位于 [returns.py](../src/quanttoolskit/returns.py)。

输入与输出均为 `[date, ticker]` MultiIndex DataFrame，输入包含价格列（默认
`close`），输出为以指标名命名的单列 DataFrame。计算前重新排序，输入顺序不影响结果。
结构与读取边界见 [项目数据结构约定](data-structure.md)。

## 使用示例

```python
from quanttoolskit import future_returns, historical_return
from quanttoolskit.data import load_prices, to_date_ticker_frame

prices = to_date_ticker_frame(df=load_prices(db="data/sp500.db"))

# 截至当天的历史表现，可用于动量或反转特征。
momentum = historical_return(df=prices, n_periods=21)

# 未来收益标签，只在事后生成。
label = future_returns(df=prices, n_periods=5, gap=1)
```

## 参数与计算口径

| 函数 | 参数默认值 | 公式 | 输出列名 |
| --- | --- | --- | --- |
| `historical_return` | `n_periods=5, price_col="close"` | `price[t] / price[t - n_periods] - 1` | `historical_return_{n_periods}` |
| `future_returns` | `n_periods=5, gap=1, price_col="close"` | `price[t + gap + n_periods] / price[t + gap] - 1` | `forward_return_{n_periods}_gap_{gap}` |

`n_periods` 必须是大于零的整数，`gap` 必须是非负整数；布尔值不接受。
默认未来标签在下一条交易记录的收盘价入场，持有 5 期后出场。

## 缺失值与使用限制

- 期数按每只股票自己的交易记录计数，不跨股票取值，不自动补齐交易日。
- 收益率以小数表示；历史或未来记录不足、端点价格缺失时为 NaN，不填补价格。
- 重复键、缺失日期或 ticker、非正价格会明确报错；价格校验由内部
  `validate_prices` 完成。长表必须先用 `to_date_ticker_frame` 转换。
- `future_returns` 使用未来数据，只用于事后生成标签或评估预测，不能进入特征。

验证见 [test_returns.py](../tests/test_returns.py) 和
[test_dataframe_contract.py](../tests/test_dataframe_contract.py)。
