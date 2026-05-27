from datetime import date, datetime
from decimal import Decimal
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode

def test_contractspec_holds_fields():
    s = ContractSpec(fut_symbol="CDF", underlying="2330",
                     underlying_type=UnderlyingType.STOCK, mult=2000,
                     spot_execution_board="整股", execution_mode=ExecutionMode.CONTINUOUS,
                     tax_class="stock", settlement_date=date(2026, 6, 17))
    assert s.mult == 2000 and s.tax_class == "stock"

def test_quote_is_frozen():
    q = Quote(symbol="2330", bid=Decimal("100"), ask=Decimal("100.5"),
              bid_qty=5000, ask_qty=4000, qty_unit="share", last=Decimal("100.2"),
              source_timestamp=datetime(2026,5,27,9,30), received_timestamp=datetime(2026,5,27,9,30),
              session="regular", market_board="整股", status="normal")
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.bid = Decimal("1")
