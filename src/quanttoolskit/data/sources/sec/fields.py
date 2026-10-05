"""标准字段 -> XBRL 科目的映射。

各家公司对同一个经济含义会用不同的 XBRL 科目(如收入在 ASC 606 之后从
SalesRevenueNet 换成了 RevenueFromContractWithCustomerExcludingAssessedTax),
这里给每个标准字段列一个按优先级排列的候选科目表。标准化时**在同一份申报文件
内部**、对同一个期间按优先级取第一个命中的科目, 实际用的科目记在 `concept` 列里,
方便事后核对口径。

个别用非标科目的公司可以在 TICKER_FIELD_OVERRIDES 里单独指定优先级。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PeriodKind = Literal["instant", "duration"]


@dataclass(frozen=True)
class FieldSpec:
    """一个标准字段的定义。

    Attributes:
        concepts: 候选科目, 写成 "taxonomy:Concept", 越靠前优先级越高。
        unit: companyfacts 里的单位, 如 "USD"、"shares"、"USD/shares"。
        kind: "instant"(时点, 资产负债表类)或 "duration"(期间, 利润表/现金流量表类)。
        additive: 期间值能否相减得到单季值(金额类可以; EPS、加权股数不行)。
    """

    concepts: tuple[str, ...]
    unit: str
    kind: PeriodKind
    additive: bool = False


def _g(*names: str) -> tuple[str, ...]:
    return tuple(f"us-gaap:{name}" for name in names)


FIELDS: dict[str, FieldSpec] = {
    # ------------------------------------------------ 利润表(期间)
    # 银行/券商的季报只有净收入(扣利息支出后), 10-K 里 Revenues 和它往往并存,
    # 放在最前面保证同一家公司各期口径一致; 普通公司没有这个科目, 不受影响
    "revenue": FieldSpec(
        _g(
            "RevenuesNetOfInterestExpense",
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "cost_of_revenue": FieldSpec(
        _g(
            "CostOfRevenue",
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
            "CostOfServices",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "gross_profit": FieldSpec(_g("GrossProfit"), "USD", "duration", additive=True),
    "rd_expense": FieldSpec(
        _g("ResearchAndDevelopmentExpense"), "USD", "duration", additive=True
    ),
    "operating_income": FieldSpec(
        _g("OperatingIncomeLoss"), "USD", "duration", additive=True
    ),
    "interest_expense": FieldSpec(
        _g("InterestExpense"), "USD", "duration", additive=True
    ),
    "pretax_income": FieldSpec(
        _g(
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "income_tax": FieldSpec(
        _g("IncomeTaxExpenseBenefit"), "USD", "duration", additive=True
    ),
    # 归母净利润优先; ProfitLoss 含少数股东损益, 只作兜底
    "net_income": FieldSpec(
        _g(
            "NetIncomeLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "ProfitLoss",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "eps_basic": FieldSpec(
        _g("EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"),
        "USD/shares",
        "duration",
    ),
    "eps_diluted": FieldSpec(
        _g("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
        "USD/shares",
        "duration",
    ),
    "shares_diluted_avg": FieldSpec(
        _g("WeightedAverageNumberOfDilutedSharesOutstanding"), "shares", "duration"
    ),
    # ------------------------------------------------ 资产负债表(时点)
    "total_assets": FieldSpec(_g("Assets"), "USD", "instant"),
    "current_assets": FieldSpec(_g("AssetsCurrent"), "USD", "instant"),
    "cash": FieldSpec(
        _g(
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            "Cash",
        ),
        "USD",
        "instant",
    ),
    "total_liabilities": FieldSpec(_g("Liabilities"), "USD", "instant"),
    "current_liabilities": FieldSpec(_g("LiabilitiesCurrent"), "USD", "instant"),
    "long_term_debt": FieldSpec(
        _g("LongTermDebtNoncurrent", "LongTermDebt"), "USD", "instant"
    ),
    # 归母权益优先; 含少数股东权益的合并口径只作兜底
    "total_equity": FieldSpec(
        _g(
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        "USD",
        "instant",
    ),
    # 封面股数(dei)的时点是封面日期, 通常比报告期末晚一个多月, 比资产负债表里的更新
    "shares_outstanding": FieldSpec(
        (
            "dei:EntityCommonStockSharesOutstanding",
            "us-gaap:CommonStockSharesOutstanding",
        ),
        "shares",
        "instant",
    ),
    # ---------------------------------------- 现金流量表(期间; 10-Q 通常只有累计值)
    "operating_cash_flow": FieldSpec(
        _g(
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "capex": FieldSpec(
        _g(
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "depreciation_amortization": FieldSpec(
        _g(
            "DepreciationDepletionAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "DepreciationAndAmortization",
        ),
        "USD",
        "duration",
        additive=True,
    ),
    "dividends_paid": FieldSpec(
        _g("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
        "USD",
        "duration",
        additive=True,
    ),
    "share_repurchase": FieldSpec(
        _g("PaymentsForRepurchaseOfCommonStock"), "USD", "duration", additive=True
    ),
}

# 个股科目优先级覆盖: {ticker: {field: (concept, ...)}}, 例如
# {"XYZ": {"revenue": ("us-gaap:RevenuesNetOfInterestExpense",)}}
TICKER_FIELD_OVERRIDES: dict[str, dict[str, tuple[str, ...]]] = {}


def get_field_concepts(field: str, ticker: str | None = None) -> tuple[str, ...]:
    """返回某个标准字段在某只股票上的候选科目(已应用个股覆盖)。

    Raises:
        KeyError: 未定义的字段。
    """
    spec = FIELDS[field]
    if ticker:
        custom = TICKER_FIELD_OVERRIDES.get(ticker.upper(), {}).get(field)
        if custom:
            return tuple(custom)
    return spec.concepts
