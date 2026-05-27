from datetime import date, datetime
from decimal import Decimal
from arbscan.models import (ContractSpec, Quote, DividendEvent, ContractAdjustment,
                            UnderlyingType, ExecutionMode)
from arbscan.engine.eligibility import evaluate_eligibility

SETTLE = date(2026, 6, 17)
SPEC = ContractSpec("CDF", "2330", UnderlyingType.STOCK, 2000, "整股",
                    ExecutionMode.CONTINUOUS, "stock", SETTLE)

def _q(symbol, recv, bidq=5000, askq=5000, status="normal"):
    return Quote(symbol, Decimal("100.5"), Decimal("100"), bidq, askq, "share",
                 Decimal("100.2"), recv, recv, "regular", "整股", status)

NOW = datetime(2026, 5, 27, 9, 30, 0)

def test_cross_ex_dividend_excluded():
    divs = [DividendEvent("2330", date(2026, 6, 10), Decimal("5"), False)]
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), divs, [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "跨除息" in flags

def test_adjusted_contract_excluded():
    adj = [ContractAdjustment("CDF", date(2026, 6, 5), "配股", True)]
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), [], adj, NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "調整型" in flags

def test_stale_quote_excluded():
    old = datetime(2026, 5, 27, 9, 0, 0)
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", old), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "過期" in flags

def test_low_liquidity_excluded():
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW, bidq=1000), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "量不足" in flags

def test_odd_lot_is_display_only():
    spec = ContractSpec("QABC", "2330", UnderlyingType.STOCK, 100, "零股",
                        ExecutionMode.ODD_LOT_CALL_AUCTION, "stock", SETTLE)
    ok, flags = evaluate_eligibility(spec, _q("QABC", NOW), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert not ok and "display_only" in flags

def test_clean_contract_eligible():
    ok, flags = evaluate_eligibility(SPEC, _q("CDF", NOW), _q("2330", NOW), [], [], NOW,
                                     stale_ms=3000, max_cross_leg_ms=500)
    assert ok and flags == ()
