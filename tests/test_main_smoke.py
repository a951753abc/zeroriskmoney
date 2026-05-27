from decimal import Decimal
from datetime import date, datetime
from arbscan.models import ContractSpec, Quote, UnderlyingType, ExecutionMode
from arbscan.engine.cost import FeePolicy
from arbscan.feed.mock import MockFeed
from arbscan.scanner import Scanner
from arbscan.main import run_once

def test_run_once_smoke():
    now = datetime(2026,5,27,9,30)
    spec = ContractSpec("CDF","2330",UnderlyingType.STOCK,2000,"整股",
                        ExecutionMode.CONTINUOUS,"stock",date(2026,6,17))
    fee = FeePolicy(Decimal("0.0004275"), {"整股": Decimal("20")}, Decimal("20"),
                    {"stock": Decimal("0.003")}, Decimal("0.00002"))
    feed = MockFeed({})
    q = lambda s,b,a: Quote(s,Decimal(b),Decimal(a),9000,9000,"share",Decimal(a),now,now,"regular","整股","normal")
    feed.set_quote("CDF", q("CDF","101","101")); feed.set_quote("2330", q("2330","100","100"))
    sc = Scanner([spec], feed, fee, Decimal("0.02"), Decimal("0.135"), Decimal("0.1"),
                 Decimal("0"), Decimal("0"), Decimal("50"), 3000, 500)
    n = run_once(sc, now, as_of="09:30", data_version="ref@09:00", render=False)
    assert n == 1
