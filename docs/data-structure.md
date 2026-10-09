# 项目数据结构约定

2026-10-09 更新。数据读取与计算结果使用不同的返回类型：

- 数据源最终输出必须经过 `to_date_ticker_frame(df=raw)`, 返回 pandas
  **MultiIndex DataFrame**, 指标或行情字段作为列。
- 因子计算、分桶、收益率、波动率及策略的单结果返回 **pd.Series**。
  用 `Series.name` 标明含义；多结果函数保留 DataFrame, 不自动合成或删除字段。

数据 DataFrame 的索引恰好为 `[date, ticker]`, 顺序固定。date 为 pandas
日期时间, 键非空且唯一, 按 date/ticker 升序排列。
逐证券计算的 Series 保留对应的 `[date, ticker]` 索引, 不跨 ticker 对齐或滚动。
多个组合逐日输出时也保留双层索引, ticker 使用组合名称, 例如 `QUANTILE_0`。
单一组合 benchmark 返回按日期排序的 DatetimeIndex Series, name 为 `nav`。
仓位 Series 表示的数值、单位与名称由具体接口说明, 不把分桶编号当作仓位权重。

`to_date_ticker_frame` 保留所有数据列且不修改输入, 转换日期并排序,
拒绝缺失键或重复 `(date, ticker)`。已有标准索引也可再次转换。
`validate_prices(df=prices, price_col="close")` 只校验已转换行情的价格列,
保留索引顺序, 不负责索引转换。缺失值保留, 不补零、不自动补齐交易日。
收益、波动率和动量因子拒绝未经转换的长表, 期数按每只股票自己的记录计数。

数据库、下载源和写入层保留来源 schema。原始 SQL 查询可返回长表,
但 date/ticker 数据进入公开计算输入前必须通过上述转换入口。
成员名单没有交易日期, SEC 原始申报具有字段、期间和版本等额外维度,
不能直接设置唯一的 date/ticker 索引。
基本面进入计算前须选定可见版本、期间长度, 再将 field 透视成列；见
[data 详细调用指南](../src/quanttoolskit/data/USAGE.md)。

迁移后的单指标调用使用 `result.name`、`result.loc[(date, ticker)]`,
不再使用 `result.columns` 或 `result.loc[(date, ticker), 指标列名]`。
需要将计算结果附加到行情表时, 使用 `prices.join(result)`；需要把多个结果
组成多列数据时, 在调用方使用 `pd.concat([factor_a, factor_b], axis=1)`。
单一组合 benchmark 使用 `nav.loc[date]`, 不再传入 portfolio_ticker, 如需组合名称可在调用方 rename。
`set_datetime_index` 保留函数名, 仍要求 ticker 并返回双层索引 DataFrame,
新代码使用 `to_date_ticker_frame`。

返回类型的调整不改变计算口径。横截面标准化仍按 date 逐列计算,
使用样本标准差 `ddof=1`；缺失、零标准差或有效样本不足时输出 NaN。
`zscore_by_date` 单列输入返回同名 Series, 多列返回同列 DataFrame, 零列仍返回 DataFrame。
`simple_bucket` 返回名为 bucket 的 Series；`vol_bucket` 保留 vol_bucket/bucket 两列 DataFrame。
两者输出分组编号, 不表示仓位权重。
横截面分桶仍按 date 独立计算, 样本不足与重复分位边界行为保留。
buy-and-hold benchmark 固定首日成员与份额, 后续成员不加入,
缺少固定成员报价时当日净值为 NaN。

**迁移状态**：收益率、波动率、累计对数收益、动量、反转、单因子 Z-score、普通分桶、
买入持有净值和分位数组示范已同步新返回类型, 包含空结果的名称与索引。
AGENTS.md 的分位数组代码与可运行源文件一致。
多因子 Z-score 和带波动分层号的 vol_bucket 继续返回多列 DataFrame。

具体计算口径见 [收益率](returns.md)、[波动率](volatility.md)、
[累计对数收益与动量](momentum.md)、[反转因子](reversal.md)、
[indicators](../src/quanttoolskit/indicators/README.md)、
[portfolio](../src/quanttoolskit/portfolio/README.md) 和
[performance](../src/quanttoolskit/performance/README.md)。
Qlib 社区行情的下载、转换与入库见 [使用说明](qlib-community-integration.md)。

[返回项目首页](../README.md)
