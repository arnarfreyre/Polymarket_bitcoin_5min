--DROP TABLE IF EXISTS btc_trades;

-- One row per trade in Polymarket "Bitcoin Up or Down" 5-minute markets.
-- Source: Data API  GET /trades?market=<conditionId>   (taker-only by default: each trade appears once,
-- the sum of SIZE = the market's volume)
-- Every field of the trade object is kept (camelCase -> UPPER_SNAKE), plus SECS_INTO_WINDOW of pm_window.py.
-- transactionHash is TX and proxyWallet is WALLET, as in the trades csv of pm_window.py.
CREATE TABLE IF NOT EXISTS btc_trades
(
    -- market
    SLUG                     VARCHAR,             -- btc-updown-5m-<window start unix> (= the trade's slug)
    CONDITION_ID             VARCHAR,             -- conditionId
    EVENT_SLUG               VARCHAR,             -- eventSlug: empty on a few trades
    TITLE                    VARCHAR,             -- title
    ICON                     VARCHAR,             -- icon

    -- trade
    TIMESTAMP                TIMESTAMPTZ,         -- timestamp (whole seconds)
    SECS_INTO_WINDOW         INTEGER,             -- timestamp - window start (unix seconds)
    SIDE                     VARCHAR,             -- BUY / SELL
    OUTCOME                  VARCHAR,             -- Up / Down
    OUTCOME_INDEX            INTEGER,             -- outcomeIndex: 0 = Up, 1 = Down
    ASSET                    VARCHAR,             -- CLOB token id
    PRICE                    DOUBLE,
    SIZE                     DOUBLE,
    TX                       VARCHAR,             -- transactionHash

    -- trader
    WALLET                   VARCHAR,             -- proxyWallet
    NAME                     VARCHAR,
    PSEUDONYM                VARCHAR,
    BIO                      VARCHAR,
    PROFILE_IMAGE            VARCHAR,             -- profileImage
    PROFILE_IMAGE_OPTIMIZED  VARCHAR              -- profileImageOptimized
);
