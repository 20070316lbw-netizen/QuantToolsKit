# 项目数据结构约定

本项目所有后续量化计算的数据输入、输出统一使用 pandas **MultiIndex DataFrame**：
索引恰好为 `[date, ticker]`（顺序固定）, date 为 pandas 日期时间, 键非空且唯一,
按 date/ticker 升序排列, 指标作为列。即使只有一个指标也返回 DataFrame。
计算内部可以临时使用 Series；对外计算接口不能返回 Series 或单层 DatetimeIndex。

读取后统一使用 `to_date_ticker_frame(df=raw)` 转换, 保留所有数据列且不修改输入。
`validate_prices(df=prices, price_col="close")` 只校验已转换行情的价格列,
保留索引顺序, 不负责索引转换。收益、波动率和动量因子内部会调用它。
已有标准索引也可再次转换。缺失值保留, 不补零、不自动补齐交易日。
收益、波动率和动量因子拒绝未经转换的长表, 期数按每只股票自己的记录计数。

数据库、下载源和写入层保留原始表结构；成员名单没有交易日期, SEC 原始申报
具有字段、期间和版本等额外维度, 不能直接设置唯一的 date/ticker 索引。
基本面进入计算前须选定可见版本、期间长度, 再将 field 透视成列；见
[data 详细调用指南](../src/quanttoolskit/data/USAGE.md)。这些属于读取边界,
后续 factors、indicators、portfolio、performance、plotting 都遵循上述计算结构。

这是接口变更：原来使用 `result.name` 的调用改用 `result.columns`, 取标量使用
`result.loc[(date, ticker), 指标列名]`；合并指标使用 `pd.concat([...], axis=1)`。
`set_datetime_index` 保留函数名, 但现在要求 ticker 并返回双层索引, 新代码使用
`to_date_ticker_frame`。

动量与单期对数收益同样返回单列 DataFrame, 具体列名及窗口口径见
[动量因子](momentum.md) 和 [收益率](returns.md)。

横截面标准化保留全部 date/ticker 键与因子列, 按 date 逐列计算,
使用样本标准差（ddof=1）；缺失、零标准差或有效样本不足时输出 NaN。
见 [indicators](../src/quanttoolskit/indicators/README.md)。

横截面分桶也保留输入的全部 date/ticker 键, 按 date 独立计算, 样本不足时
返回 NaN。组合聚合指标使用代表组合的 ticker（例如 BUY_AND_HOLD）, 每个
观察日期输出一行；缺少固定成员报价时净值为 NaN。接口与迁移说明见
[portfolio](../src/quanttoolskit/portfolio/README.md) 和
[performance](../src/quanttoolskit/performance/README.md)。

[返回项目首页](../README.md)
