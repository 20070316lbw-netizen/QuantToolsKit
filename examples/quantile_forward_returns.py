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
) -> pd.DataFrame:
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
        [date, ticker] DataFrame, 单列 forward_return, 小数收益率。
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
        >>> scores = zscore_by_date(scores)
        >>> result = quantile_forward_returns(scores, prices, freq=20, n_quantiles=2)
        >>> result["forward_return"].round(6).tolist()
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
    aligned = buckets.join(forward.rename("forward_return"))
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
    return pd.DataFrame({"forward_return": means.to_numpy()}, index=index).sort_index()


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
    standardized_scores = zscore_by_date(scores)
    result = quantile_forward_returns(
        standardized_scores, prices, freq=20, n_quantiles=2
    )
    print(result)
    # 跨调仓日的平均值仅用于展示；若新增计算接口, 也须返回标准 DataFrame。
    print(result.groupby(level="ticker")["forward_return"].mean())
