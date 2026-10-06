"""CLOB API — Order book data, pricing, and historical prices."""

import requests
from ._base import CLOB_BASE


class CLOBAPI:
    """Order book data, pricing, and historical prices."""

    BASE = CLOB_BASE

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def get_book(self, token_id: str) -> dict:
        """Fetch full order book for a token."""
        resp = self.session.get(f"{self.BASE}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    def get_books(self, token_ids: list[str]) -> list[dict]:
        """Batch fetch order books."""
        resp = self.session.post(f"{self.BASE}/books", json=token_ids)
        resp.raise_for_status()
        return resp.json()

    def get_price(self, token_id: str, side: str = "BUY") -> dict:
        """Fetch best price for a token. side: 'BUY' or 'SELL'."""
        params = {"token_id": token_id, "side": side}
        resp = self.session.get(f"{self.BASE}/price", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_prices(self, token_ids: list[str], side: str = "BUY") -> list[dict]:
        """Batch fetch prices."""
        resp = self.session.post(
            f"{self.BASE}/prices",
            json=[{"token_id": tid, "side": side} for tid in token_ids],
        )
        resp.raise_for_status()
        return resp.json()

    def get_midpoint(self, token_id: str) -> dict:
        """Fetch midpoint price for a token."""
        resp = self.session.get(f"{self.BASE}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    def get_spread(self, token_id: str) -> dict:
        """Fetch bid-ask spread for a token."""
        resp = self.session.get(f"{self.BASE}/spread", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()

    def get_last_trade_price(self, token_id: str) -> dict:
        """Fetch last executed trade price."""
        resp = self.session.get(
            f"{self.BASE}/last-trade-price", params={"token_id": token_id}
        )
        resp.raise_for_status()
        return resp.json()

    def get_price_history(self, market: str, interval: str = "max",
                          fidelity: int = 60) -> list[dict]:
        """
        Fetch historical price time series.

        Args:
            market: The condition ID (market ID) or token ID.
            interval: Time range - '1d', '1w', '1m', '3m', '1y', 'max'.
            fidelity: Data point interval in minutes (e.g., 60 = hourly).

        Returns:
            List of {t: timestamp, p: price} data points.
        """
        params = {"market": market, "interval": interval, "fidelity": fidelity}
        resp = self.session.get(f"{self.BASE}/prices-history", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_markets(self, next_cursor: str = "") -> dict:
        """Fetch paginated list of all CLOB markets."""
        params = {"next_cursor": next_cursor} if next_cursor else {}
        resp = self.session.get(f"{self.BASE}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_simplified_markets(self, next_cursor: str = "") -> dict:
        """Fetch paginated simplified market list."""
        params = {"next_cursor": next_cursor} if next_cursor else {}
        resp = self.session.get(f"{self.BASE}/simplified-markets", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_tick_size(self, token_id: str) -> dict:
        """Fetch minimum price increment."""
        resp = self.session.get(f"{self.BASE}/tick-size", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()
