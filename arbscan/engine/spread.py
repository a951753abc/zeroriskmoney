from decimal import Decimal

def entry_spread(f_bid: Decimal, s_ask: Decimal) -> Decimal:
    """進場價差/單位 = 期貨買價 − 現股賣價（保守報價，不加股利 D）。"""
    return f_bid - s_ask

def quoted_edge_profit(f_bid: Decimal, s_ask: Decimal, mult: int) -> Decimal:
    """帳面毛價差（未扣任何成本/緩衝）。"""
    return entry_spread(f_bid, s_ask) * mult
