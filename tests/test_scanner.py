from decimal import Decimal
from datetime import date, datetime
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode
from arbscan.engine.cost import FeePolicy
from arbscan.feed.mock import MockFeed
from arbscan.scanner import Scanner

NOW = datetime(2026,5,27,9,30)
FEE = FeePolicy(Decimal("0.0004275"), {"整股": Decimal("20"), "零股": Decimal("1")},
                Decimal("20"), {"stock": Decimal("0.003"), "etf": Decimal("0.001")}, Decimal("0.00002"))
SPEC = ContractSpec("CDF","2330",UnderlyingType.STOCK,2000,"整股",
                    ExecutionMode.CONTINUOUS,"stock",date(2026,6,17))

def _q(sym, bid, ask):
    return Quote(sym, Decimal(bid), Decimal(ask), 9000, 9000, "share",
                 Decimal(ask), NOW, NOW, "regular", "整股", "normal")

def _scanner(threshold):
    return Scanner(specs=[SPEC], feed=MockFeed({}), fee=FEE,
                   funding_rate=Decimal("0.02"), initial_margin_rate=Decimal("0.135"),
                   price_limit=Decimal("0.1"), entry_buffer=Decimal("0"), exit_buffer=Decimal("0"),
                   min_net_threshold=Decimal(threshold), stale_ms=3000, max_cross_leg_ms=500)

def test_scanner_produces_result_for_clean_spread():
    sc = _scanner("0")
    sc.feed.set_quote("CDF", _q("CDF","100.5","100.5"))
    sc.feed.set_quote("2330", _q("2330","100","100"))
    results = sc.scan(NOW)
    assert len(results) == 1 and results[0].fut_symbol == "CDF"
    assert results[0].estimated_net_before_funding.quantize(Decimal("0.01")) == Decimal("180.98")

def test_scanner_flags_new_signal_over_threshold():
    sc = _scanner("50")
    sc.feed.set_quote("CDF", _q("CDF","101","101")); sc.feed.set_quote("2330", _q("2330","100","100"))
    new = sc.detect_new_signals(sc.scan(NOW))
    assert "CDF" in {r.fut_symbol for r in new}
