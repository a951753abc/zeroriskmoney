from decimal import Decimal
from arbscan.models import ArbResult
from arbscan.ui.table import build_table

def test_build_table_one_row():
    r = ArbResult("CDF","2330",Decimal("0.5"),Decimal("1000"),Decimal("180.98"),
                  Decimal("80"),Decimal("951976.51"),Decimal("1100000"),Decimal("0.05"),21,())
    table = build_table([r], as_of="2026-05-27 09:30", data_version="ref@09:00")
    assert table.row_count == 1
