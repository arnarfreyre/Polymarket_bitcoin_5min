"""Gamma API — Market/event metadata, search, and discovery."""

import requests
from ._base import GAMMA_BASE


class GammaAPI:
    """Market/event metadata, search, and discovery."""

    BASE = GAMMA_BASE

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def get_events(self, limit: int = 100, offset: int = 0, active: bool = True,
                   closed: bool = False, order: str = "volume24hr",
                   ascending: bool = False, **filters) -> list[dict]:
        """Fetch events (groups of related markets)."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
            **filters,
        }
        resp = self.session.get(f"{self.BASE}/events", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_event(self, event_id: str) -> dict:
        """Fetch a single event by ID."""
        resp = self.session.get(f"{self.BASE}/events/{event_id}")
        resp.raise_for_status()
        return resp.json()

    def get_event_by_slug(self, slug: str) -> dict:
        """Fetch a single event by slug."""
        resp = self.session.get(f"{self.BASE}/events/slug/{slug}")
        resp.raise_for_status()
        return resp.json()

    def get_markets(self, limit: int = 100, offset: int = 0, active: bool = True,
                    closed: bool = False, order: str = "volume24hr",
                    ascending: bool = False, **filters) -> list[dict]:
        """Fetch individual markets."""
        params = {
            "limit": limit,
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
            **filters,
        }
        resp = self.session.get(f"{self.BASE}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_market(self, market_id: str) -> dict:
        """Fetch a single market by condition ID."""
        resp = self.session.get(f"{self.BASE}/markets/{market_id}")
        resp.raise_for_status()
        return resp.json()

    def get_market_by_slug(self, slug: str) -> dict:
        """Fetch a single market by slug."""
        resp = self.session.get(f"{self.BASE}/markets/slug/{slug}")
        resp.raise_for_status()
        return resp.json()

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search markets by text query."""
        params = {"q": query, "limit": limit}
        resp = self.session.get(f"{self.BASE}/public-search", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_tags(self) -> list[dict]:
        """Fetch available market tags/categories."""
        resp = self.session.get(f"{self.BASE}/tags")
        resp.raise_for_status()
        return resp.json()
