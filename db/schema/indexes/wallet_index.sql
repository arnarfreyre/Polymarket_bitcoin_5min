
--DROP INDEX IF EXISTS wallet_index;
CREATE INDEX IF NOT EXISTS wallet_index ON bitcoin_5m_trades (PROXY_WALLET);