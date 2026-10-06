"""
Polymarket API client for data collection.

Three public APIs (no auth needed for read-only data):
- Gamma API: Market/event discovery and metadata
- CLOB API:  Order books, prices, historical price data
- Data API:  Trades, positions, open interest, volume

Usage:
    from polymarket_api import PolymarketClient
    client = PolymarketClient()

    # Or import individual APIs:
    from polymarket_api.gamma import GammaAPI
    from polymarket_api.clob import CLOBAPI
    from polymarket_api.data import DataAPI
"""

from .gamma import GammaAPI
from .clob import CLOBAPI
from .data import DataAPI
from .client import PolymarketClient

__all__ = ["GammaAPI", "CLOBAPI", "DataAPI", "PolymarketClient"]
