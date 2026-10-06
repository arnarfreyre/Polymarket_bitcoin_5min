"""Data API — Trade history, positions, open interest, and volume analytics."""

import requests
from ._base import DATA_BASE


class DataAPI:
    """Trade history, positions, open interest, and volume analytics."""

    BASE = DATA_BASE

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def get_trades(self, market: str | None = None, limit: int = 100,
                   offset: int = 0, **filters) -> list[dict]:
        """Fetch trade history, optionally filtered by market."""
        params = {"limit": limit, "offset": offset, **filters}
        if market:
            params["market"] = market
        resp = self.session.get(f"{self.BASE}/trades", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_positions(self, market: str | None = None, limit: int = 100,
                      offset: int = 0) -> list[dict]:
        """Fetch open positions."""
        params = {"limit": limit, "offset": offset}
        if market:
            params["market"] = market
        resp = self.session.get(f"{self.BASE}/positions", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_closed_positions(self, market: str | None = None, limit: int = 100,
                             offset: int = 0) -> list[dict]:
        """Fetch resolved/closed positions."""
        params = {"limit": limit, "offset": offset}
        if market:
            params["market"] = market
        resp = self.session.get(f"{self.BASE}/closed-positions", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_holders(self, market: str) -> list[dict]:
        """Fetch top holders for a market."""
        resp = self.session.get(f"{self.BASE}/holders", params={"market": market})
        resp.raise_for_status()
        return resp.json()

    def get_live_volume(self, event_id: str | None = None) -> dict:
        """Fetch real-time volume data."""
        params = {}
        if event_id:
            params["event_id"] = event_id
        resp = self.session.get(f"{self.BASE}/live-volume", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_open_interest(self, market: str | None = None) -> dict:
        """Fetch open interest data."""
        params = {}
        if market:
            params["market"] = market
        resp = self.session.get(f"{self.BASE}/oi", params=params)
        resp.raise_for_status()
        return resp.json()
