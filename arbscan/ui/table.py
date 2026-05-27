from decimal import Decimal
from rich.table import Table
from arbscan.models import ArbResult
from arbscan.engine.eligibility import BLOCKING_FLAGS

def build_table(results: list[ArbResult], as_of: str, data_version: str, min_net_threshold: Decimal = Decimal("0")) -> Table:
    t = Table(title=f"準套利訊號 (indicative，下單前自行覆核)  報價:{as_of}  參考:{data_version}")
    for col in ("期貨","標的","價差","保守淨利","年化%","壓力本金(聯合)","結算倒數","旗標"):
        t.add_column(col)
    for r in results:
        blocked = any(f in BLOCKING_FLAGS for f in r.flags)
        style = "dim" if blocked else ("green" if r.estimated_net_conservative > min_net_threshold else "")
        t.add_row(r.fut_symbol, r.underlying, f"{r.entry_spread:.2f}",
                  f"{r.estimated_net_conservative:,.0f}", f"{r.annualized*100:.2f}",
                  f"{r.stress_capital_joint:,.0f}", str(r.days_held),
                  ",".join(r.flags), style=style)
    return t
