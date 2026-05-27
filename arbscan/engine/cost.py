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

def funding_cost(base_reserved_cash: Decimal, funding_rate: Decimal, days_held: int) -> Decimal:
    """正常占用資金的資金成本（務實近似，不與壓力本金重複懲罰）。"""
    return base_reserved_cash * funding_rate * Decimal(days_held) / Decimal(365)

def estimated_net_before_funding(gross: Decimal, txn_cost: Decimal) -> Decimal:
    return gross - txn_cost

def estimated_net_conservative(net_before_funding: Decimal, funding: Decimal,
                               entry_buffer: Decimal, exit_buffer: Decimal) -> Decimal:
    """達標與排序依據：扣資金成本、人工執行 buffer、結算基差 buffer 後的保守淨利。"""
    return net_before_funding - funding - entry_buffer - exit_buffer
