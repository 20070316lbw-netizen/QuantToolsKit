# performance：买入持有基准

[返回项目首页](../../../README.md) · [数据结构约定](../../../docs/data-structure.md)

```python
from quanttoolskit.data.transfer_data import to_date_ticker_frame
from quanttoolskit.performance import buy_and_hold_nav

prices = to_date_ticker_frame(df=raw)  # raw 含 date、ticker、adj_close
nav = buy_and_hold_nav(
    prices, initial_capital=1.0, price_col="adj_close", portfolio_ticker="BENCH"
)
```

`buy_and_hold_nav(price, initial_capital=1.0, *, price_col="close",
portfolio_ticker="BUY_AND_HOLD")` 接受标准行情 DataFrame, 返回单列 `nav`,
索引为 `[date, ticker]`, ticker 是代表整个组合的名称。

首个观察日期有有效价格的证券形成固定成员池, 期初资金等分后买入固定份额：
`nav[t] = initial_capital × mean(price[t, i] / price[first_date, i])`。
之后权重自然漂移, 后续上市证券不加入。直接根据固定份额估值, 无需逐日收益连乘。未计交易费用、现金利息或单独的分红现金流；输入价格须采用一致的
复权口径, 可选择 `adj_close`。

某日期任何固定成员缺少记录或价格, 整组净值为 NaN, 不填零或前向填充；
后续报价完整时可恢复计算。只输出输入中出现的日期, 不补交易日。
首日全部价格缺失时报错。价格必须为有限正数或缺失值, 期初资金必须为有限
正数, 组合名称必须为非空字符串。空输入返回有双层索引和 `nav` 列的空表。

原实现接受价格宽表、返回 Series, 且实际每日等权再平衡。现在须先将行情
转换为标准长表索引, 返回结果通过 `nav.loc[(date, "BENCH"), "nav"]` 取值。
数值口径也已变为严格的固定份额买入持有。

## 完整调用示范

[分位组前瞻收益示范](../../../examples/quantile_forward_returns.py) 展示标准行情和
打分表的构造、逐日 Z-score 标准化、分桶、按公共调仓日取收益端点, 以及保留 date/ticker 索引的组收益。
从仓库根目录运行：

```bash
python examples/quantile_forward_returns.py
```

示范中 40 个工作日、4 只证券, 只有 D 从 1 线性上涨到 2。
每 20 条行情日期调仓, 分成两组, 首日的两组前瞻收益分别为 0 和约 0.256410。
分组收益平均时仅使用有效的入场、出场价格；完全无有效收益的组为 NaN。
此示范是事后因子评价, 使用未来价格。
