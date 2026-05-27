from decimal import Decimal
from arbscan.engine.spread import entry_spread, quoted_edge_profit

def test_entry_spread_uses_conservative_quotes():
    assert entry_spread(Decimal("100.5"), Decimal("100")) == Decimal("0.5")

def test_quoted_edge_profit_times_mult():
    assert quoted_edge_profit(Decimal("100.5"), Decimal("100"), 2000) == Decimal("1000.0")
