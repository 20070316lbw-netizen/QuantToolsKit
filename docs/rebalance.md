# rebalance: 调仓日历

[返回项目首页](../README.md) · [收益率与净值](returns.md)

实现位于 [rebalance.py](../src/quanttoolskit/rebalance.py)。两个函数均使用所有
证券共享的交易日历, 不按单只证券各自的记录计数。

## 使用

```python
from quanttoolskit.rebalance import rebalance_dates, rebalance_dates_belong

# prices 已通过 to_date_ticker_frame 转为 [date, ticker] DataFrame。
calendar = prices.index.get_level_values("date").unique().sort_values()
selected = rebalance_dates(calendar, freq=21)
belong = rebalance_dates_belong(calendar, freq=21)
```

| 函数 | 输出 | 含义 |
| --- | --- | --- |
| `rebalance_dates(dates, freq)` | DatetimeIndex | 从最早日期开始, 取第 0、freq、2*freq 条日期 |
| `rebalance_dates_belong(dates, freq)` | Series, name 为 `rebalance_date` | 每个日期所属区间的起始调仓日 |

`dates` 必须是 DatetimeIndex, 可以乱序、重复或为空, 不接受 NaT。
两个函数都先排序去重, 保留输入索引名、时区和日期精度, 不修改输入。
`freq` 无默认值, 必须是正整数, 接受 NumPy 整数, 不接受布尔值。
间隔按输入日历中存在的日期计数, 不是自然日数; 缺少的交易日不会自动补齐。
调用方须提供适合策略的完整日历, 某个日期所有证券均缺记录时,
仅从行情提取日期不会包含该日。

区间为 `[本次调仓日, 下次调仓日)`, 调仓日自己开启新区间。
最后一个区间保留所有剩余日期; `freq` 超过日历长度时所有日期归属首日。
空日历返回同日期类型的空索引或 Series, 仍会检查 `freq`。
非 DatetimeIndex 输入报 TypeError; 无效 `freq` 或缺失日期报 ValueError。

这两个函数只生成日期或区间标签, 不构造仓位、不执行交易。
完整可运行示范见 [rebalance_nav.py](../examples/rebalance_nav.py),
其中证券 B 缺少两天记录, 调仓节奏仍由共同行情日历决定。
运行 `python examples/rebalance_nav.py`; 验证见
[test_rebalance.py](../tests/test_rebalance.py) 和
[test_rebalance_nav_example.py](../tests/test_rebalance_nav_example.py)。
