from decimal import Decimal
from datetime import datetime
from arbscan.models import ContractSpec, ArbResult
from arbscan.feed.base import QuoteFeed
from arbscan.engine.cost import (FeePolicy, transaction_cost, funding_cost,
                                  estimated_net_before_funding, estimated_net_conservative)
from arbscan.engine.spread import entry_spread, quoted_edge_profit
from arbscan.engine.capital import stress_capital
from arbscan.engine.rank import annualized_return
from arbscan.engine.eligibility import evaluate_eligibility

_BLOCKING = ("跨除息", "調整型", "過期", "量不足", "display_only")

class Scanner:
    def __init__(self, specs, feed: QuoteFeed, fee: FeePolicy, funding_rate: Decimal,
                 initial_margin_rate: Decimal, price_limit: Decimal, entry_buffer: Decimal,
                 exit_buffer: Decimal, min_net_threshold: Decimal, stale_ms: int,
                 max_cross_leg_ms: int, dividends=None, adjustments=None):
        self.specs = list(specs); self.feed = feed; self.fee = fee
        self.funding_rate = funding_rate; self.initial_margin_rate = initial_margin_rate
        self.price_limit = price_limit; self.entry_buffer = entry_buffer
        self.exit_buffer = exit_buffer; self.min_net_threshold = min_net_threshold
        self.stale_ms = stale_ms; self.max_cross_leg_ms = max_cross_leg_ms
        self.dividends = dividends or []; self.adjustments = adjustments or []
        self._alerted: set[str] = set()

    def _days_held(self, spec: ContractSpec, now: datetime) -> int:
        return max((spec.settlement_date - now.date()).days + 2, 1)

    def _trading_days(self, spec: ContractSpec, now: datetime) -> int:
        return max(int((spec.settlement_date - now.date()).days * 5 / 7), 1)

    def scan(self, now: datetime) -> list[ArbResult]:
        out: list[ArbResult] = []
        for spec in self.specs:
            fut = self.feed.get_quote(spec.fut_symbol)
            spot = self.feed.get_quote(spec.underlying)
            if fut is None or spot is None:
                continue
            eligible, flags = evaluate_eligibility(spec, fut, spot, self.dividends,
                                                   self.adjustments, now, self.stale_ms,
                                                   self.max_cross_leg_ms)
            spread = entry_spread(fut.bid, spot.ask)
            gross = quoted_edge_profit(fut.bid, spot.ask, spec.mult)
            txn = transaction_cost(spot.ask, fut.bid, spot.ask, spot.ask, spec.mult,
                                   spec.spot_execution_board, spec.tax_class, self.fee)
            nbf = estimated_net_before_funding(gross, txn)
            n_days = self._trading_days(spec, now)
            days_held = self._days_held(spec, now)
            cap_A = stress_capital(spot.ask, fut.bid, spec.mult, self.initial_margin_rate,
                                   n_days, self.price_limit)
            cap_joint = stress_capital(spot.ask, fut.bid, spec.mult, self.initial_margin_rate,
                                       n_days, self.price_limit, stress_mult=Decimal("3"))
            base_reserved = spot.ask * spec.mult + fut.bid * spec.mult * self.initial_margin_rate
            fund = funding_cost(base_reserved, self.funding_rate, days_held)
            net = estimated_net_conservative(nbf, fund, self.entry_buffer, self.exit_buffer)
            ann = annualized_return(net, cap_joint, days_held)
            out.append(ArbResult(spec.fut_symbol, spec.underlying, spread, gross, nbf, net,
                                 cap_A, cap_joint, ann, days_held, flags))
        out.sort(key=lambda r: (any(f in _BLOCKING for f in r.flags), -r.annualized))
        return out

    def detect_new_signals(self, results: list[ArbResult]) -> list[ArbResult]:
        """合格、保守淨利達標、且本輪新出現者。"""
        new = []
        live = set()
        for r in results:
            qualified = (not any(f in _BLOCKING for f in r.flags)
                         and r.estimated_net_conservative > self.min_net_threshold)
            if qualified:
                live.add(r.fut_symbol)
                if r.fut_symbol not in self._alerted:
                    new.append(r)
        self._alerted = live
        return new
