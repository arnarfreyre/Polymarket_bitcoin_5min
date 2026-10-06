"""Unified client wrapping all three Polymarket APIs."""

import requests
from .gamma import GammaAPI
from .clob import CLOBAPI
from .data import DataAPI


class PolymarketClient:
    """
    Unified client wrapping all three Polymarket APIs.

    Usage:
        client = PolymarketClient()

        # Discover markets
        events = client.gamma.get_events(limit=10)

        # Get price history for a market
        history = client.clob.get_price_history(market=token_id, interval="1m")

        # Get trade data
        trades = client.data.get_trades(market=condition_id, limit=500)
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "polymarket-ml-client/0.1",
        })
        self.gamma = GammaAPI(self.session)
        self.clob = CLOBAPI(self.session)
        self.data = DataAPI(self.session)
