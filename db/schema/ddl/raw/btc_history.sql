--DROP TABLE IF EXISTS btc_history;

-- ~1 point a minute of price history per outcome token of a Polymarket "Bitcoin Up or Down" 5-minute market.
-- Source: CLOB API  GET /prices-history?market=<token id>&startTs=<start - 3600>&endTs=<start + 600>&fidelity=1
-- The history[] points (t, p) of pm_window.py, plus SLUG, TOKEN_ID and OUTCOME to tell the series apart.
CREATE TABLE IF NOT EXISTS btc_history
(
    -- market
    SLUG                     VARCHAR,             -- btc-updown-5m-<window start unix>
    TOKEN_ID                 VARCHAR,             -- CLOB token id the history was asked for
    OUTCOME                  VARCHAR,             -- Up / Down
    -- price
    TIMESTAMP                TIMESTAMPTZ,         -- history[].t
    PRICE                    DOUBLE               -- history[].p
);
