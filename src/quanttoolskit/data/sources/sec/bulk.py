"""SEC companyfacts 的纯 JSON 解析层，不下载、不写库。

同一期间可能在多份申报文件中重复出现，甚至发生重述。解析器保留这些版本，
不取最新值；科目优先级、单位口径和单季推导由 normalize 模块处理。
原始表中的 fy/fp 是申报文件的标签，不能用来替代事实的起止日期。
"""

from collections.abc import Iterable
from typing import Any

import pandas as pd

from ...universe import format_cik

RAW_FACT_COLUMNS = [
    "cik",
    "taxonomy",
    "concept",
    "unit",
    "period_start",
    "period_end",
    "value",
    "fy",
    "fp",
    "form",
    "accn",
    "filed",
    "frame",
]


def parse_company_facts(
    payload: dict[str, Any],
    concepts: Iterable[str] | None = None,
) -> pd.DataFrame:
    """把 companyfacts JSON 展开成长表。

    Args:
        payload: companyfacts 接口返回的 JSON。
        concepts: 只保留这些科目, 写成 "taxonomy:Concept"(如 "us-gaap:Revenues");
            None 表示全部保留。

    Returns:
        DataFrame, 列为 RAW_FACT_COLUMNS。时点型(instant)事实的 period_start 为 NaT;
        fy/fp/form 描述的是**申报文件**的财年/期间, 不一定是这条事实本身所属的期间
        (比较期数据尤其如此), 期间以 period_start/period_end 为准。
    """
    wanted = set(concepts) if concepts is not None else None
    cik = format_cik(payload.get("cik", 0))
    rows: list[tuple] = []

    for taxonomy, facts in (payload.get("facts") or {}).items():
        for concept, body in facts.items():
            if wanted is not None and f"{taxonomy}:{concept}" not in wanted:
                continue
            for unit, items in (body.get("units") or {}).items():
                for item in items:
                    rows.append(
                        (
                            cik,
                            taxonomy,
                            concept,
                            unit,
                            item.get("start"),
                            item.get("end"),
                            item.get("val"),
                            item.get("fy"),
                            item.get("fp"),
                            item.get("form"),
                            item.get("accn"),
                            item.get("filed"),
                            item.get("frame"),
                        )
                    )

    df = pd.DataFrame(rows, columns=RAW_FACT_COLUMNS)
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed"] = pd.to_datetime(df["filed"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("Int64")
    for col in ("cik", "taxonomy", "concept", "unit", "fp", "form", "accn", "frame"):
        df[col] = df[col].astype("string")
    return df.dropna(subset=["period_end", "value", "accn", "filed"]).reset_index(
        drop=True
    )
