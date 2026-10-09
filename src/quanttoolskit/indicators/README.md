# indicators：指标与横截面标准化

[返回项目首页](../../../README.md) · [数据结构约定](../../../docs/data-structure.md)

`zscore_by_date(df, *, date_level="date")` 对每个日期、每一列因子独立标准化：
`z = (值 - 当日均值) / 当日样本标准差`, 标准差使用 `ddof=1`。

输入为 `[date, ticker]` MultiIndex DataFrame, 一列一个因子；输出保留所有键和
原列名, 按索引排序, 不修改输入。
单因子返回 Series, name 为原列名；多因子返回 DataFrame, 保留全部因子列。均值和标准差忽略缺失值, 缺失值仍为 NaN。
常数截面、只有一个有效值或全缺失的因子截面返回 NaN, 不人为赋值为零。
数值字符串可转换；无穷值或无法转换的非数值报错。
`date_level` 仅接受契约规定的 `date`。空输入按列数遵循相同返回规则；零列输入返回零列 DataFrame。

## 标准化后检验分位组收益

以下调用使用 [完整可运行示例](../../../examples/quantile_forward_returns.py)：

```python
from examples.quantile_forward_returns import quantile_forward_returns, sample_data
from quanttoolskit.indicators import zscore_by_date

scores, prices = sample_data()
standardized = zscore_by_date(scores)
result = quantile_forward_returns(
    standardized.to_frame(), prices, freq=20, n_quantiles=2
)
print(result)
```

在仓库根目录运行 `python examples/quantile_forward_returns.py` 即可看到两组收益
分别为 0 和约 0.256410。`examples` 是仓库示范目录, 不属于安装后的公共包 API。

单因子正标准差下, 标准化是严格递增变换, 不改变分数排序及本例分桶结果。
多因子会逐列标准化, 不自动合成打分, 合成方法应由调用方明确指定。
此处前瞻收益使用未来价格, 仅用于事后评估。

原单列输出的 `standardized["score"]` 改为直接使用 standardized。
下一步需要 DataFrame 时显式调用 `.to_frame()`；多因子 DataFrame 的列选择方式不变。
