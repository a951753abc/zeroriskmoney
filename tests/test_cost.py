from decimal import Decimal
from arbscan.engine.cost import FeePolicy, spot_commission, transaction_cost

FEE = FeePolicy(
    spot_rate=Decimal("0.0004275"),
    spot_min_fee={"整股": Decimal("20"), "零股": Decimal("1")},
    fut_fee_per_lot=Decimal("20"),
    tax_spot={"stock": Decimal("0.003"), "etf": Decimal("0.001")},
    tax_fut=Decimal("0.00002"),
)

def test_spot_commission_applies_min_fee():
    assert spot_commission(Decimal("10000"), "整股", FEE) == Decimal("20")
    assert spot_commission(Decimal("200000"), "整股", FEE) == Decimal("85.5")

def test_transaction_cost_matches_spec_4_7():
    cost = transaction_cost(
        s_ask=Decimal("100"), f_bid=Decimal("100.5"),
        p_est=Decimal("100"), f_settle_est=Decimal("100"),
        mult=2000, board="整股", tax_class="stock", fee=FEE)
    assert cost.quantize(Decimal("0.01")) == Decimal("819.02")
