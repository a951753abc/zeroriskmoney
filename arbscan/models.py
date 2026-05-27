from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class UnderlyingType(str, Enum):
    STOCK = "stock"
    ETF = "etf"

class ExecutionMode(str, Enum):
    CONTINUOUS = "continuous"
    ODD_LOT_CALL_AUCTION = "odd_lot_call_auction"

@dataclass(frozen=True)
class ContractSpec:
    fut_symbol: str
    underlying: str
    underlying_type: UnderlyingType
    mult: int                       # 契約乘數（股數/受益權單位）
    spot_execution_board: str       # "整股" / "零股"
    execution_mode: ExecutionMode
    tax_class: str                  # "stock"->0.003, "etf"->0.001
    settlement_date: date

@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_qty: int                    # 已正規化為「標的單位」(share/unit)
    ask_qty: int
    qty_unit: str                   # provenance: "lot"/"share"/"odd_share"/"etf_unit"
    last: Decimal
    source_timestamp: datetime
    received_timestamp: datetime
    session: str
    market_board: str
    status: str                     # "normal"/"halt"/...

@dataclass(frozen=True)
class DividendEvent:
    underlying: str
    ex_date: date
    cash_dividend: Decimal          # 每股現金股利
    has_stock_dividend: bool        # 配股 -> 需排除

@dataclass(frozen=True)
class ContractAdjustment:
    fut_symbol: str
    effective_date: date
    kind: str                       # "除息"/"配股"/"減資"/"合併"
    changes_multiplier: bool

@dataclass(frozen=True)
class ArbResult:
    fut_symbol: str
    underlying: str
    entry_spread: Decimal
    quoted_edge_profit: Decimal
    estimated_net_before_funding: Decimal
    estimated_net_conservative: Decimal
    stress_capital_A: Decimal
    stress_capital_joint: Decimal
    annualized: Decimal
    days_held: int
    flags: tuple[str, ...] = field(default_factory=tuple)
    indicative: bool = True
