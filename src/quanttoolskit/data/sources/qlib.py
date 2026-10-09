"""读取本地社区 Qlib 日行情, 在返回边界统一为 date/ticker DataFrame。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..transfer_data import to_date_ticker_frame


def read_qlib_prices(
    *,
    data_dir: str | Path,
    start: str | date | datetime,
    end: str | date | datetime,
    tickers: str | Sequence[str] | None = None,
    market: str | None = None,
) -> pd.DataFrame:
    """读取本地 Qlib 的全部可用日频字段, 保留上游复权结果。

    Args:
        data_dir: 直接包含 calendars、features 的本地 provider 目录。
        start: 查询起始日, 包含当日, 必须是无时区且不含盘中时间的日期。
        end: 查询截止日, 包含当日, 不早于 start；实际结果取源交易日历交集。
        tickers: 单个代码或代码序列, 默认 None, 与 market 必须二选一。
            代码统一大写, 例如 SH600000；空序列或不存在的证券报错。
        market: 历史股票池名称, 默认 None, 例如 csi300 或 all。
            成分有效区间由 Qlib 处理, 不替换成当前成员名单。

    Returns:
        [date, ticker] MultiIndex DataFrame, 日期无时区, 键唯一且升序排列。
        保留源包全部 *.day.bin 字段, 去掉字段名前的 $, 数值不再复权或舍入。
        保留 adjclose、factor 等来源名称与单位, 不合成 adj_close。
        缺失值保留；无匹配日期/成员时返回具有相同字段的空标准 DataFrame。
        不下载、不写库、不补报价。调用会初始化进程内的 Qlib provider,
        不支持同一进程并发切换不同 provider。

    Raises:
        ImportError: 未安装可选依赖 pyqlib, 提示安装 quanttoolskit[qlib]。
        TypeError: ticker/market 或日期参数类型不符合要求。
        ValueError: 日期、选择器、字段名或返回数据键不符合约定。
        FileNotFoundError: 本地日历、行情文件或指定市场/证券目录不存在。
        OSError: Qlib 来源文件读取失败。

    Example:
        安装 qlib 可选依赖后, 以下例子自行创建最小本地行情, 无需下载。

        >>> import tempfile
        >>> import numpy as np
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     root = Path(folder)
        ...     (root / "calendars").mkdir()
        ...     _ = (root / "calendars/day.txt").write_text(
        ...         "2024-01-02\\n2024-01-03\\n"
        ...     )
        ...     (root / "features/sh600000").mkdir(parents=True)
        ...     np.array([0, 1, 2], dtype="<f4").tofile(
        ...         root / "features/sh600000/close.day.bin"
        ...     )
        ...     prices = read_qlib_prices(
        ...         data_dir=root, start="2024-01-02", end="2024-01-03",
        ...         tickers="SH600000",
        ...     )
        >>> prices["close"].tolist()
        [1.0, 2.0]
    """
    bounds = []
    for name, value in (("start", start), ("end", end)):
        if not isinstance(value, str | date | datetime):
            raise TypeError(f"{name} 必须是日期")
        day = pd.Timestamp(value)
        if pd.isna(day) or day.tz is not None or day != day.normalize():
            raise ValueError(f"{name} 必须是无时区的日频日期")
        bounds.append(day)
    if bounds[0] > bounds[1]:
        raise ValueError("end 不能早于 start")
    if (tickers is None) == (market is None):
        raise ValueError("tickers 与 market 必须二选一")

    root = Path(data_dir).expanduser().resolve()
    if not (root / "calendars/day.txt").is_file():
        raise FileNotFoundError(f"缺少交易日历: {root / 'calendars/day.txt'}")
    if market is not None:
        if not isinstance(market, str):
            raise TypeError("market 必须是字符串")
        market = market.lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", market):
            raise ValueError("market 必须是有效股票池名称")
        if not (root / "instruments" / f"{market}.txt").is_file():
            raise FileNotFoundError(f"缺少历史股票池: {market}")
    else:
        if not isinstance(tickers, str | Sequence):
            raise TypeError("tickers 必须是代码或代码序列")
        symbols = [tickers] if isinstance(tickers, str) else list(tickers)
        if not symbols:
            raise ValueError("tickers 不能为空")
        if any(not isinstance(symbol, str) for symbol in symbols):
            raise TypeError("ticker 必须是字符串")
        symbols = [symbol.upper() for symbol in symbols]
        if any(not re.fullmatch(r"[A-Z0-9_]+", symbol) for symbol in symbols):
            raise ValueError("ticker 必须是有效 Qlib 代码")
        if len(set(symbols)) != len(symbols):
            raise ValueError("tickers 不能重复")
        for symbol in symbols:
            if not any((root / "features" / symbol.lower()).glob("*.day.bin")):
                raise FileNotFoundError(f"缺少证券日行情: {symbol}")

    # 取整个来源的字段并集, 避免选择不同证券时悄悄丢失辅助字段。
    available = {
        path.name.removesuffix(".day.bin")
        for path in (root / "features").glob("*/*.day.bin")
    }
    if not available:
        raise FileNotFoundError("来源没有日频行情字段")
    if any(
        not re.fullmatch(r"[a-z_][a-z0-9_]*", field)
        or field in {"date", "ticker", "release_tag"}
        for field in available
    ):
        raise ValueError("来源字段名无效或与索引/来源列冲突")
    leading = ["open", "high", "low", "close", "volume", "factor"]
    fields = [field for field in leading if field in available]
    fields.extend(sorted(available.difference(fields)))

    try:
        import qlib
        from qlib.constant import REG_CN
        from qlib.data import D
    except ModuleNotFoundError as exc:
        if exc.name != "qlib":
            raise
        raise ImportError("请安装可选依赖: pip install 'quanttoolskit[qlib]'") from exc

    qlib.init(
        provider_uri=str(root),
        region=REG_CN,
        kernels=1,
        expression_cache=None,
        dataset_cache=None,
    )
    instruments = D.instruments(market) if market is not None else symbols
    frame = D.features(
        instruments=instruments,
        fields=[f"${field}" for field in fields],
        start_time=bounds[0],
        end_time=bounds[1],
        freq="day",
        disk_cache=0,
    )
    raw = frame.reset_index().rename(
        columns={"datetime": "date", "instrument": "ticker"}
    )
    raw = raw.rename(columns=lambda column: column.removeprefix("$"))
    return to_date_ticker_frame(df=raw)
