from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class FeePolicy:
    spot_rate: Decimal
    spot_min_fee: dict[str, Decimal]
    fut_fee_per_lot: Decimal
    tax_spot: dict[str, Decimal]
    tax_fut: Decimal

def spot_commission(notional: Decimal, board: str, fee: FeePolicy) -> Decimal:
    return max(notional * fee.spot_rate, fee.spot_min_fee[board])

def transaction_cost(s_ask: Decimal, f_bid: Decimal, p_est: Decimal,
                     f_settle_est: Decimal, mult: int, board: str,
                     tax_class: str, fee: FeePolicy) -> Decimal:
    buy = spot_commission(s_ask * mult, board, fee)
    sell = spot_commission(p_est * mult, board, fee)
    securities_tax = p_est * mult * fee.tax_spot[tax_class]
    fut_fee = fee.fut_fee_per_lot * 2
    fut_tax = (f_bid + f_settle_est) * mult * fee.tax_fut
    return buy + sell + securities_tax + fut_fee + fut_tax
