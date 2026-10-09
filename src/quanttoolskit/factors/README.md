# factors：因子计算

[返回项目首页](../../../README.md)

用于构建量化因子, 输入与输出遵循
[项目数据结构约定](../../../docs/data-structure.md)。

| 模块 | 公开接口 | 使用说明 |
| --- | --- | --- |
| `momfactor` | `cumulative_log_returns`、`momentum_12_1`、兼容接口 `momentum` | [累计对数收益与动量](../../../docs/momentum.md) |
| `reversal` | `reversal` | [短期反转因子](../../../docs/reversal.md) |

公开接口可从 `quanttoolskit.factors` 或对应子包导入。
`cumulative_log_returns` 可计算窗口累计对数收益率, 也可作为动量特征。
自包含的 [可运行示范](../../../examples/return_factors.py) 包含收益、反转、
横截面标准化与分桶。
