
--DROP INDEX IF EXISTS market_index;
CREATE INDEX IF NOT EXISTS market_index ON bitcoin_5m_trades (EVENT_SLUG);