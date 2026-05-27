from datetime import datetime
from arbscan.models import (ContractSpec, Quote, DividendEvent, ContractAdjustment,
                            ExecutionMode)

_BLOCKING = ("跨除息", "調整型", "過期", "量不足", "display_only")

def _stale(q: Quote, now: datetime, stale_ms: int) -> bool:
    return (now - q.received_timestamp).total_seconds() * 1000 > stale_ms

def evaluate_eligibility(spec: ContractSpec, fut: Quote, spot: Quote,
                         dividends: list[DividendEvent], adjustments: list[ContractAdjustment],
                         now: datetime, stale_ms: int, max_cross_leg_ms: int) -> tuple[bool, tuple[str, ...]]:
    flags: list[str] = []
    today = now.date()
    for d in dividends:
        if d.underlying == spec.underlying and today <= d.ex_date <= spec.settlement_date:
            flags.append("跨除息"); break
    for a in adjustments:
        if a.fut_symbol == spec.fut_symbol and today <= a.effective_date <= spec.settlement_date:
            flags.append("調整型"); break
    if _stale(fut, now, stale_ms) or _stale(spot, now, stale_ms):
        flags.append("過期")
    if abs((fut.source_timestamp - spot.source_timestamp).total_seconds()) * 1000 > max_cross_leg_ms:
        flags.append("過期")
    if fut.bid_qty < spec.mult or spot.ask_qty < spec.mult or fut.status != "normal" or spot.status != "normal":
        flags.append("量不足")
    if spec.execution_mode == ExecutionMode.ODD_LOT_CALL_AUCTION:
        flags.append("display_only")
    eligible = not any(f in _BLOCKING for f in flags)
    return eligible, tuple(dict.fromkeys(flags))
