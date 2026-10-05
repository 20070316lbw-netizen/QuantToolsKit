# volatility：波动率

[返回项目首页](../README.md) · [收益率](returns.md)

实现位于 [volatility.py](../src/quanttoolskit/volatility.py)。

输入与输出均为 `[date, ticker]` MultiIndex DataFrame，输入包含价格列（默认
`close`），输出为以指标名命名的单列 DataFrame。计算前重新排序，输入顺序不影响结果。
结构与读取边界见 [项目数据结构约定](data-structure.md)。

## 使用示例

```python
from quanttoolskit import forward_volatility, history_vol
from quanttoolskit.data import load_prices, to_date_ticker_frame

prices = to_date_ticker_frame(df=load_prices(db="data/sp500.db"))

# 截至当天的历史波动特征。
vol = history_vol(df=prices, window=21)

# 未来持有区间的波动标签，只在事后生成。
forward_risk = forward_volatility(df=prices, window=21, gap=1)
```

## 参数与计算口径

定义日简单收益率 `r[t] = price[t] / price[t - 1] - 1`。
两个函数均计算样本标准差（`ddof=1`），不年化，输出小数波动率。

| 函数 | 参数默认值 | 窗口 | 输出列名 |
| --- | --- | --- | --- |
| `history_vol` | `window=21, price_col="close"` | `r[t - window + 1] ... r[t]` | `volatility_{window}` |
| `forward_volatility` | `window=21, gap=1, price_col="close"` | `r[t + gap + 1] ... r[t + gap + window]` | `forward_volatility_{window}_gap_{gap}` |

`window` 必须是至少为 2 的整数，`gap` 必须是非负整数；布尔值不接受。
历史波动率需要 `window + 1` 条有效价格记录才能首次计算。
未来波动率使用 `price[t + gap]` 到 `price[t + gap + window]` 的
`window + 1` 个价格，计算 `window` 个单期收益率的标准差。

## 缺失值与使用限制

- 期数按每只股票自己的交易记录计数，不跨股票滚动，不自动补齐交易日。
- 记录不足或窗口内收益率缺失时为 NaN，价格缺失不填补。
- 重复键、缺失日期或 ticker、非正价格会明确报错；价格校验由内部
  `validate_prices` 完成。长表必须先用 `to_date_ticker_frame` 转换。
- `forward_volatility` 使用未来数据，只用于事后生成标签或评估预测，不能进入特征。

验证见 [test_volatility.py](../tests/test_volatility.py) 和
[test_dataframe_contract.py](../tests/test_dataframe_contract.py)。
