from decimal import Decimal

def fut_cash_at_day(f_bid: Decimal, mult: int, initial_margin_rate: Decimal,
                    k: int, price_limit: Decimal, stress_mult: Decimal = Decimal("1"),
                    broker_addon: Decimal = Decimal("0")) -> Decimal:
    """第 k 日（天天漲停）期貨腿需備現金：累積虧損補繳 + 放大的原始保證金。"""
    f_k = f_bid * (Decimal("1") + price_limit) ** k
    loss = (f_k - f_bid) * mult
    margin = f_k * mult * initial_margin_rate * stress_mult + broker_addon
    return loss + margin

def stress_capital(s_ask: Decimal, f_bid: Decimal, mult: int,
                   initial_margin_rate: Decimal, n_days: int, price_limit: Decimal,
                   stress_mult: Decimal = Decimal("1"), broker_addon: Decimal = Decimal("0"),
                   entry_fees: Decimal = Decimal("0"), max_limit_up_days: int | None = None) -> Decimal:
    """壓力本金 = 現股款 + entry_fees + 情境內逐日期貨需備現金之最大值。"""
    spot_cost = s_ask * mult
    k_max = n_days if max_limit_up_days is None else min(n_days, max_limit_up_days)
    worst = max(
        fut_cash_at_day(f_bid, mult, initial_margin_rate, k, price_limit, stress_mult, broker_addon)
        for k in range(0, k_max + 1)
    )
    return spot_cost + entry_fees + worst
