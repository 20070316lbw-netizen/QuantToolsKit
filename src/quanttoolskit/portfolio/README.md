# portfolio：横截面分桶

[返回项目首页](../../../README.md) · [数据结构约定](../../../docs/data-structure.md)

输入必须是已转换的 `[date, ticker]` MultiIndex DataFrame, 输出排序并保留全部
输入行, 不修改输入。每个日期独立分组, 不跨日期混合证券。

```python
from quanttoolskit.data.transfer_data import to_date_ticker_frame
from quanttoolskit.portfolio import simple_bucket, vol_bucket

signals = to_date_ticker_frame(df=raw)  # raw 含 date、ticker、score、vol
buckets = simple_bucket(signals, score_col="score", n_quantiles=5)
layered = vol_bucket(signals, n_vol_groups=3, n_quantiles=5)
```

- `simple_bucket(df, *, score_col="score", n_quantiles=5)` 返回单列 `bucket`。
  每日有效分数不足 n_quantiles 时, 当日桶号全为 NaN。
- `vol_bucket(df, *, score_col="score", vol_col="vol", n_quantiles=5,
  n_vol_groups=5)` 返回 `vol_bucket` 和 `bucket` 两列。仅分数与波动率都有值
  的证券参加, 当日有效样本少于两种分组数量的乘积时, 两列全为 NaN。
  先按波动率分层, 再在各层内对分数分桶；层内样本不足时保留层号, 桶号为 NaN。

桶号从 0 开始, 数值越高, 分数或波动率越高。使用 `pd.qcut`, 相同值不人为
拆开, 重复分位边界会减少实际组数；全部相同时没有可用分位区间, 输出 NaN。
缺失值不填补, 数值字符串可转换, 非数值及无穷值报错。分组数量必须为正整数,
不接受布尔值。空输入保留双层索引及输出列。

原 `simple_bucket(Series)` 调用需改为标准 DataFrame；原 `vol_bucket` 返回的
Series 改为使用结果的 `bucket` 列, 层号单独保存在 `vol_bucket` 列。

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
