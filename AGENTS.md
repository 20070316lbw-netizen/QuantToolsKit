# 项目数据结构

`2026-10-09 更新`
QuantToolsKit 内函数接口满足:

- 数据源流出最后形态强制流经 `to_date_ticker_frame` 函数, 传回 `['date', 'ticker']` MultiIndex DataFrame。
- 因子计算, 仓位构造, 收益率, 波动率, 策略比如等权买入持仓不变的 `benchmark` 的单结果返回 `pd.Series`; 多结果保留 DataFrame。

数据库、下载源、存储写入和成员/原始申报查询保留来源 schema。读取后, date/ticker 表通过 `to_date_ticker_frame` 转换, 再进入计算。
`validate_prices` 仅校验已转换行情的价格列, 不负责索引转换。
基本面先按时点筛选版本、选定期间并将字段透视成列, 禁止直接丢弃重复键。
缺失值不自动填补, 交易记录不自动补齐, 分组位移和滚动必须按 ticker 隔离。
详细约定见 docs/data-structure.md；修改契约时同步更新该文档、模块文档和测试。
主 README 只保留项目概览、目录与安装；模块使用说明放在独立文档并从目录链接。

# 提交信息

所有 commit 信息统一使用 `类型: 中文描述` 格式, 例如 `feat: 新增动量因子`。
类型可使用 feat、fix、docs、test、refactor、chore 等英文标识；类型标记后的描述统一使用中文。

# 注释、参数说明与调用示范

新增或修改公开计算函数时, 使用中文 docstring, 说明计算口径, 并包含：

- `Args`：输入 DataFrame 的索引、必需列、参数默认值、单位及限制。
- `Returns`：输出类型、索引、Series.name 或 DataFrame 列名、单位、缺失值和样本不足的行为。
- `Raises`：主要参数与数据校验错误。
- `Example`：自包含、可执行、具有正确预期结果的调用示例。

函数内注释解释有业务含义的选择, 例如时点对齐、缺失报价、重复分位边界；
无需逐行复述代码。示例应共用已有计算接口, 不使用未实现的函数或 `type: ignore`
掩盖输入格式问题。可运行示例及测试分别放在 examples/ 和 tests/, 模块文档链接示例。

下面以分位数组前瞻收益为示范, 对应源文件为
[examples/quantile_forward_returns.py](examples/quantile_forward_returns.py)。
输入为标准 DataFrame；先使用 zscore_by_date 逐日、逐列标准化, 再分桶。
单因子标准化返回 Series 并保留排序, 进入分桶前显式 to_frame；
常数或样本不足的截面为 NaN, 多因子返回 DataFrame, 不自动合成。
内部可使用宽表和 Series。输出保留每个调仓日,
以 QUANTILE_0 等组合名称作为 ticker, 返回名为 forward_return 的 Series,
跨日期平均值仅在展示阶段汇总。
原始示例中的自定义 date_level 固定为契约要求的 date；调仓日取公共行情
日期序列的第 0、freq、2*freq 条, 不按每只证券各自的记录数移动。
分组后的平均收益是有效端点证券的等权均值, 须明确披露该缺失值处理口径。
示例使用未来价格, 仅用于事后检验；组收益单调递增是评价目标, 并非函数保证。

以下代码与可运行源文件保持一致；修改示范时同步更新这里及其测试。

```python
"""分位数组的前瞻收益示范; 运行: python examples/quantile_forward_returns.py。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quanttoolskit.data.transfer_data import _validate_frame, validate_prices
from quanttoolskit.indicators import zscore_by_date
from quanttoolskit.portfolio import simple_bucket


def quantile_forward_returns(
    score: pd.DataFrame,
    price: pd.DataFrame,
    *,
    freq: int,
    n_quantiles: int,
    score_col: str = "score",
    price_col: str = "close",
) -> pd.Series:
    """按调仓日分桶, 计算各组到下一个调仓日的平均简单收益。

    Args:
        score: [date, ticker] DataFrame, 只含调仓日的横截面打分。
        price: [date, ticker] DataFrame, 包含完整观察日历的行情。
        freq: 调仓间隔, 正整数；按行情中所有不同日期的升序序列计数,
            从首日开始每隔 freq 条日期取一个调仓日。不是自然日数。
        n_quantiles: 正整数分组数, 须与组合构造时使用的数量一致。
        score_col: 分数列名, 默认 score。
        price_col: 价格列名, 默认 close, 可指定 adj_close。

    Returns:
        [date, ticker] MultiIndex Series, name 为 forward_return, 小数收益率。
        date 为打分日期, ticker 为 QUANTILE_0、QUANTILE_1 等组名称。
        每日使用 simple_bucket 分桶, 组内仅对入场、出场价格都有效的
        证券取等权平均；完全无有效收益的组保留 NaN, 不填补报价。
        最后一个调仓日没有下一调仓日, 收益为 NaN, 不用末日缩短持有期。
        输出全部请求的组；重复分位边界可能使部分组没有成员。
        仅用于事后检验, 使用未来数据, 不能作为当日交易信号。

    Raises:
        TypeError: 输入非 DataFrame, 或 freq/n_quantiles 非整数。
        ValueError: 索引、数据列或数值不符合约定, 参数非正数,
            或打分日期不在由 price 和 freq 确定的调仓日序列中。

    Example:
        >>> scores, prices = sample_data()
        >>> scores = zscore_by_date(scores).to_frame()
        >>> result = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
        >>> result.round(6).tolist()
        [0.0, 0.25641]
    """
    _validate_frame(score)
    if isinstance(freq, bool) or not isinstance(freq, int):
        raise TypeError("freq 必须是整数")
    if freq < 1:
        raise ValueError("freq 必须大于 0")
    prices = validate_prices(df=price, price_col=price_col).sort_index()
    if not np.isfinite(prices[price_col].dropna()).all():
        raise ValueError(f"{price_col} 必须是有限数值")
    # 共用分桶实现, 保证与组合构造的编号和重复边界处理一致。
    buckets = simple_bucket(score, score_col=score_col, n_quantiles=n_quantiles)
    dates = prices.index.get_level_values("date").unique()
    rebalance_dates = dates[::freq]
    score_dates = buckets.index.get_level_values("date").unique()
    if not score_dates.isin(rebalance_dates).all():
        raise ValueError("score 的日期必须位于调仓日序列中")
    # 宽表仅用于内部按共同日历取端点, 不按单只证券的记录数位移。
    rebalance_prices = prices[price_col].unstack("ticker").reindex(rebalance_dates)
    forward = (rebalance_prices.shift(-1) / rebalance_prices - 1).stack(
        future_stack=True
    )
    aligned = buckets.to_frame().join(forward.rename("forward_return"))
    means = aligned.groupby([pd.Grouper(level="date"), "bucket"])[
        "forward_return"
    ].mean()
    group_index = pd.MultiIndex.from_product(
        [score_dates, range(n_quantiles)], names=["date", "bucket"]
    )
    means = means.reindex(group_index)
    index = pd.MultiIndex.from_arrays(
        [
            means.index.get_level_values("date"),
            [
                f"QUANTILE_{int(group)}"
                for group in means.index.get_level_values("bucket")
            ],
        ],
        names=["date", "ticker"],
    )
    return pd.Series(means.to_numpy(), index=index, name="forward_return").sort_index()


def sample_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """40 个工作日、4 只证券；只有 D 从 1 线性上涨到 2。"""
    dates = pd.bdate_range("2024-01-01", periods=40)
    tickers = ["A", "B", "C", "D"]
    index = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    prices = pd.DataFrame({"close": 1.0}, index=index)
    prices.loc[(slice(None), "D"), "close"] = [1 + i / 39 for i in range(40)]
    scores = pd.DataFrame(
        {"score": [1.0, 2.0, 3.0, 4.0]},
        index=pd.MultiIndex.from_product(
            [dates[:1], tickers], names=["date", "ticker"]
        ),
    )
    return scores, prices


if __name__ == "__main__":
    scores, prices = sample_data()
    # 单因子标准化保留排序, 因此本例分桶和组收益不变。
    # 多因子输入会逐列标准化；合成方式须由调用方明确选择。
    standardized_scores = zscore_by_date(scores).to_frame()
    result = quantile_forward_returns(
        standardized_scores, prices, freq=20, n_quantiles=2
    )
    print(result)
    # 跨调仓日的平均值仅用于展示, 分组计算结果保留 [date, ticker] 索引。
    print(result.groupby(level="ticker").mean())
```

# 源码字符规范

编辑器可能提示 U+FF0C 全角逗号与常见源码字符 U+002C ASCII 逗号混淆。
项目源码、注释、docstring、示范与文档统一使用 ASCII 逗号 `,`;
正文逗号后加一个空格, 保留中文文字。提及全角逗号时使用 `U+FF0C`
或转义形式 `\uFF0C`, 避免再次引入触发警告的字符。
不要通过关闭 Unicode 字符提示来掩盖问题。涉及外部原始数据、解析匹配或
测试输入时, 如必须表示全角逗号, 使用转义并注明其业务用途。
