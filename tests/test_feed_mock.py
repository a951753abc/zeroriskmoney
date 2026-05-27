from decimal import Decimal
from datetime import datetime
from arbscan.feed.mock import MockFeed
from arbscan.models import Quote

def test_mock_feed_returns_seeded_quote():
    now = datetime(2026,5,27,9,30)
    q = Quote("2330", Decimal("100.5"), Decimal("100"), 5000, 5000, "share",
              Decimal("100.2"), now, now, "regular", "整股", "normal")
    feed = MockFeed({"2330": q})
    feed.subscribe(["2330"])
    assert feed.get_quote("2330").bid == Decimal("100.5")
    assert feed.get_quote("9999") is None
