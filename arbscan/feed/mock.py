from typing import Optional
from arbscan.models import Quote

class MockFeed:
    """離線假 feed：用預先植入的報價，供 scanner/engine 測試。"""
    def __init__(self, quotes: dict[str, Quote]):
        self._quotes = dict(quotes)
        self._subscribed: set[str] = set()
    def subscribe(self, symbols: list[str]) -> None:
        self._subscribed.update(symbols)
    def get_quote(self, symbol: str) -> Optional[Quote]:
        return self._quotes.get(symbol)
    def is_connected(self) -> bool:
        return True
    def set_quote(self, symbol: str, q: Quote) -> None:
        self._quotes[symbol] = q
