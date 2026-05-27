from decimal import Decimal
from arbscan.engine.cost import (funding_cost, estimated_net_before_funding,
                                  estimated_net_conservative)

def test_net_before_funding_matches_spec():
    assert estimated_net_before_funding(Decimal("1000"), Decimal("819.02")) == Decimal("180.98")

def test_funding_cost_on_base_reserved_cash():
    fc = funding_cost(Decimal("233500"), Decimal("0.02"), 30)
    assert fc.quantize(Decimal("0.01")) == Decimal("383.84")

def test_conservative_subtracts_all_buffers():
    n = estimated_net_conservative(Decimal("180.98"), Decimal("50"),
                                   entry_buffer=Decimal("60"), exit_buffer=Decimal("40"))
    assert n == Decimal("30.98")
