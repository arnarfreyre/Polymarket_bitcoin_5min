DROP TABLE IF EXISTS positions;

CREATE TABLE IF NOT EXISTS positions
(
    -- key
    PROXY_WALLET      VARCHAR,
    CONDITION_ID      VARCHAR,
    EVENT_SLUG        VARCHAR,      -- from bitcoin_5m_markets
    NAME              VARCHAR,

    -- trades
    N_TRADES          BIGINT,
    BUY_USD           DOUBLE,
    SELL_USD          DOUBLE,
    BUY_UP_USD        DOUBLE,
    BUY_DOWN_USD      DOUBLE,
    BUY_SHARES        DOUBLE,
    NET_UP_SHARES     DOUBLE,       -- bought - sold
    NET_DOWN_SHARES   DOUBLE,

    -- result
    PNL               DOUBLE,       -- sell proceeds - buy cost + net winning shares * $1
    FIRST_TIME        TIMESTAMPTZ,
    LAST_TIME         TIMESTAMPTZ
);
