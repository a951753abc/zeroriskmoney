from decimal import Decimal
from arbscan.engine.rank import annualized_return

def test_annualized_basic():
    r = annualized_return(Decimal("1000"), Decimal("100000"), 30)
    assert r.quantize(Decimal("0.0001")) == Decimal("0.1217")

def test_annualized_guards_zero():
    assert annualized_return(Decimal("100"), Decimal("0"), 30) == Decimal("0")
    assert annualized_return(Decimal("100"), Decimal("100000"), 0) == Decimal("0")
