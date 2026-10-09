# factors：短期反转因子

[返回项目首页](../README.md) · [累计对数收益与动量](momentum.md) · [收益率](returns.md)

实现位于 [reversal](../src/quanttoolskit/factors/reversal/)。
输入为 `[date, ticker]` MultiIndex DataFrame, 默认价格列为 `adj_close`。
单结果返回排序后的同索引 Series；结构见 [数据结构约定](data-structure.md)。

## 使用示例

```python
import pandas as pd

from quanttoolskit.data import to_date_ticker_frame
from quanttoolskit.factors import reversal

prices = to_date_ticker_frame(
    df=pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3),
            "ticker": ["A"] * 3,
            "adj_close": [1.0, 2.0, 8.0],
        }
    )
)
raw = reversal(prices, window=2, vol_adjust=False)
adjusted = reversal(prices, window=2)
print(raw.iloc[-1].round(6))  # -2.079442
print(adjusted.iloc[-1].round(6))  # -4.242641
```

可从 `quanttoolskit.factors` 或 `quanttoolskit.factors.reversal` 导入。
[可运行示范](../examples/return_factors.py) 将累计对数收益、反转与现有
`zscore_by_date`、`simple_bucket` 接口连接起来。运行：

```bash
python examples/return_factors.py
```

## 参数与计算口径

| 参数 | 默认值 | 含义与限制 |
| --- | --- | --- |
| `window` | `21` | 单期对数收益窗口数, 正整数；波动调整时至少为 2 |
| `skip` | `0` | 跳过最近的交易记录数, 非负整数 |
| `vol_adjust` | `True` | 必须是布尔值；是否除以同窗口的单期对数收益样本标准差 |
| `price_col` | `"adj_close"` | 价格列名, 可指定 `"close"`；非缺失价格须为正数 |

`window` 和 `skip` 不接受布尔值。令 `r[t] = log(P[t]) - log(P[t-1])`,
对应日期 t 的窗口是 `r[t-skip-window+1]` 到 `r[t-skip]`, 包含两端。
未调整的反转值为这些收益的和取负, 完整窗口等于
`log(P[t-skip-window]) - log(P[t-skip])`。
因此下跌得到正值, 上涨得到负值；使用截至 t-skip 的历史数据, 不使用未来价格。

调整后的值将上式除以**同一窗口**的 `std(r, ddof=1)`。
分母是单期对数收益的样本标准差, 不年化, 不乘 `sqrt(window)`。
分子与分母先计算, 再一起按 ticker 后移 skip 期。
这与 `zscore_by_date` 的同日跨证券标准化含义不同。

输出名为 `reversal_{window}_skip_{skip}`, 调整时追加 `_vol`。
未调整结果单位为累计对数收益, 调整后为无量纲比值, 两者都不是百分数。

## 缺失值、校验与数值边界

- 期数按每只证券自己的记录计数, 不补齐停牌或缺少的日期, 不跨证券滚动或位移。
- 每只证券前 `window + skip` 条记录为 NaN, 首次有效值至少需要
  `window + skip + 1` 条价格记录。
- 窗口内任一价格缺失时为 NaN, 即使两个端点有效；不填补价格,
  缺失离开窗口后恢复计算。跳过区间内价格不参与对应日期计算。
- 波动调整时样本标准差为零或缺失输出 NaN, 不用零或无限大替代。
  极小的正标准差不截断；浮点舍入也可能让理论常数收益出现极小正标准差,
  因子值因此可能很大。当前未引入波动率下限。
- 非 DataFrame 输入、非整数期数或非布尔值 vol_adjust 抛出 TypeError；
  非法索引、重复键、缺失键、缺少价格列、非正价格或越界期数抛出 ValueError。
  原始长表须先通过 `to_date_ticker_frame` 转换。
- 不修改输入；空输入返回同名空 Series, 保留标准索引。

验证见 [test_reversal.py](../tests/test_reversal.py)、
[test_dataframe_contract.py](../tests/test_dataframe_contract.py) 和
[示范测试](../tests/test_return_factors_example.py)。
