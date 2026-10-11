"""因子 Series 的拼接准备与本地行情试跑入口。"""

from __future__ import annotations

import pandas as pd

from quanttoolskit.data.transfer_data import _validate_frame


def to_panel(factor: pd.Series, name: str) -> pd.Series:
    """校验单因子 Series, 排序并命名, 供下游拼接或横截面标准化。

    Args:
        factor: [date, ticker] MultiIndex Series, date 为日期时间,
            键非空且唯一。上游单因子已经是此结构, 无需再 stack。
        name: 必填的非空字符串, 指定输出因子名称。

    Returns:
        按 date/ticker 排序的 Series, name 为指定名称, 单位与输入相同。
        保留全部记录及 NaN, 不填补缺失值或补齐交易记录, 不修改输入。
        样本不足产生的 NaN 原样保留, 空输入返回同索引类型的空 Series。
        多因子可用 pd.concat([...], axis=1) 拼成 DataFrame。

    Raises:
        TypeError: factor 非 Series, 或 name 非字符串。
        ValueError: 索引不符合约定, 键缺失或重复, 或 name 为空字符串。

    Example:
        >>> index = pd.MultiIndex.from_product(
        ...     [pd.to_datetime(["2024-01-01"]), ["A", "B"]],
        ...     names=["date", "ticker"],
        ... )
        >>> factor = pd.Series([0.1, float("nan")], index=index, name="mom_12_1")
        >>> result = to_panel(factor, "score")
        >>> result.name, result.iloc[0], result.isna().sum()
        ('score', np.float64(0.1), np.int64(1))
    """
    if not isinstance(factor, pd.Series):
        raise TypeError("factor 必须是 Series")
    if not isinstance(name, str):
        raise TypeError("name 必须是字符串")
    if not name.strip():
        raise ValueError("name 不能为空字符串")
    _validate_frame(factor.to_frame(name="factor"))
    return factor.sort_index().rename(name)


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from quanttoolskit.data import load_prices, to_date_ticker_frame
    from quanttoolskit.factors.momfactor import MOM_FACTORS

    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description="使用本地行情试跑经典 12-1 动量")
    parser.add_argument("--db", type=Path, default=root / "data" / "sp500.db")
    args = parser.parse_args()
    prices = to_date_ticker_frame(df=load_prices(db=args.db))
    factor_fn = MOM_FACTORS["momentum_12_1"]
    factor_result = factor_fn(df=prices)
    print(factor_result)
    print(f"总记录: {len(factor_result)}, 有效因子: {factor_result.notna().sum()}")
