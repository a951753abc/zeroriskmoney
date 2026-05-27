from decimal import Decimal
from arbscan.engine.capital import fut_cash_at_day, stress_capital

def test_stress_capital_scenario_A_matches_spec_4_7():
    cap = stress_capital(s_ask=Decimal("100"), f_bid=Decimal("100.5"), mult=2000,
                         initial_margin_rate=Decimal("0.135"), n_days=15,
                         price_limit=Decimal("0.1"))
    assert cap.quantize(Decimal("0.01")) == Decimal("951976.51")

def test_joint_stress_raises_margin_makes_capital_larger():
    base = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"))
    joint = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"),
                           stress_mult=Decimal("3"))
    assert joint > base

def test_scenario_B_capped_limit_up_days_smaller():
    full = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"))
    capped = stress_capital(Decimal("100"), Decimal("100.5"), 2000, Decimal("0.135"), 15, Decimal("0.1"),
                            max_limit_up_days=3)
    assert capped < full
