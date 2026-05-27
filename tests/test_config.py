from decimal import Decimal
import pytest
from arbscan.config import Settings, load_settings

def test_load_settings_from_toml(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text(
        'funding_rate = "0.02"\n'
        'min_net_threshold = "50"\n'
        'entry_execution_buffer = "60"\n'
        'exit_basis_buffer = "40"\n'
        'max_cross_leg_ms = 500\n'
        'stale_quote_ms = 3000\n', encoding="utf-8")
    s = load_settings(p)
    assert s.funding_rate == Decimal("0.02")
    assert s.max_cross_leg_ms == 500

def test_settings_rejects_negative_rate():
    with pytest.raises(ValueError):
        Settings(funding_rate=Decimal("-0.01"), min_net_threshold=Decimal("0"),
                 entry_execution_buffer=Decimal("0"), exit_basis_buffer=Decimal("0"),
                 max_cross_leg_ms=500, stale_quote_ms=3000)
