from decimal import Decimal

def annualized_return(net_conservative: Decimal, stress_capital: Decimal, days_held: int) -> Decimal:
    """占用資金年化（務實近似）。本金或天數非正 → 0。"""
    if stress_capital <= 0 or days_held <= 0:
        return Decimal("0")
    return net_conservative / stress_capital * Decimal("365") / Decimal(days_held)
