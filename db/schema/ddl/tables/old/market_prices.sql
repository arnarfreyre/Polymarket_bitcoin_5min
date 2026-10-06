DROP TABLE IF EXISTS market_prices;

-- One row per market per second of its 5-minute window (300 rows per market).
-- Row THE_TIME describes the state at the end of second [THE_TIME, THE_TIME + 1s).
-- Built by db/schema/tables/market_prices.sql.
CREATE TABLE IF NOT EXISTS market_prices
(
    -- market
    EVENT_SLUG        VARCHAR,
    CONDITION_ID      VARCHAR,
    EVENT_NAME        VARCHAR,      -- bitcoin_5m_markets.QUESTION
    EVENT_START_TIME  TIMESTAMPTZ,
    END_DATE          TIMESTAMPTZ,
    RESULT            VARCHAR,      -- Up / Down

    -- time
    THE_TIME          TIMESTAMPTZ,  -- EVENT_START_TIME .. END_DATE - 1s
    SECONDS_TO_END    INTEGER,      -- 300 .. 1

    -- last taker trade price at or before THE_TIME (carried forward; includes pre-window trades)
    BUY_UP            DOUBLE,
    SELL_UP           DOUBLE,
    BUY_DOWN          DOUBLE,
    SELL_DOWN         DOUBLE,

    -- bitcoin (Binance BTCUSDT 1s)
    BITCOIN_PRICE     DOUBLE,       -- CLOSE of the candle opening at THE_TIME
    BTC_START_PRICE   DOUBLE        -- OPEN of the candle opening at EVENT_START_TIME
);
