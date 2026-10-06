--DROP TABLE IF EXISTS bitcoin_prices;

-- One row per 1-second BTCUSDT spot kline from Binance.
-- Source: data.binance.vision  spot/{monthly,daily}/klines/BTCUSDT/1s (via the binance_vision package)
-- Columns mirror the kline CSV fields (snake_case -> UPPER_SNAKE).
-- Join to bitcoin_5m_markets on OPEN_TIME between EVENT_START_TIME and END_DATE.
CREATE TABLE IF NOT EXISTS bitcoin_prices
(
    -- time
    OPEN_TIME                TIMESTAMPTZ NOT NULL, -- open_time: start of the 1s candle (UTC)
    CLOSE_TIME               TIMESTAMPTZ,          -- close_time: OPEN_TIME + 999999 us

    -- price
    OPEN                     DOUBLE,
    HIGH                     DOUBLE,
    LOW                      DOUBLE,
    CLOSE                    DOUBLE,

    -- volume
    VOLUME                   DOUBLE,               -- volume: base asset (BTC)
    QUOTE_VOLUME             DOUBLE,               -- quote_volume: quote asset (USDT)
    COUNT                    BIGINT,               -- count: number of trades
    TAKER_BUY_VOLUME         DOUBLE,               -- taker_buy_volume: base asset (BTC)
    TAKER_BUY_QUOTE_VOLUME   DOUBLE,               -- taker_buy_quote_volume: quote asset (USDT)
    IGNORE                   BIGINT                -- ignore: unused field, always 0
);
