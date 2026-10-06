-- Per-second Up/Down prices of each market's 5-minute window, with the BTC price.
-- Prices are the last taker trade at or before THE_TIME, per side and outcome.
-- Trades only have whole-second timestamps; within a market the rows are stored newest-first
-- (the Data API's order), so the lowest rowid in a second is that second's last trade.
INSERT INTO market_prices
WITH GRID AS (
    SELECT
        m.EVENT_SLUG,
        m.CONDITION_ID,
        m.QUESTION AS EVENT_NAME,
        m.EVENT_START_TIME,
        m.END_DATE,
        m.RESULT,
        m.EVENT_START_TIME + to_seconds(s.s) AS THE_TIME,
        300 - s.s AS SECONDS_TO_END
    FROM bitcoin_5m_markets m
    CROSS JOIN range(0, 300) s(s)
),
LAST_TRADES AS (
    SELECT
        CONDITION_ID,
        SIDE,
        OUTCOME,
        TIMESTAMP,
        arg_min(PRICE, rowid) AS PRICE
    FROM bitcoin_5m_trades
    GROUP BY ALL
),
BUY_UP    AS (SELECT CONDITION_ID, TIMESTAMP, PRICE FROM LAST_TRADES WHERE SIDE = 'BUY'  AND OUTCOME = 'Up'),
SELL_UP   AS (SELECT CONDITION_ID, TIMESTAMP, PRICE FROM LAST_TRADES WHERE SIDE = 'SELL' AND OUTCOME = 'Up'),
BUY_DOWN  AS (SELECT CONDITION_ID, TIMESTAMP, PRICE FROM LAST_TRADES WHERE SIDE = 'BUY'  AND OUTCOME = 'Down'),
SELL_DOWN AS (SELECT CONDITION_ID, TIMESTAMP, PRICE FROM LAST_TRADES WHERE SIDE = 'SELL' AND OUTCOME = 'Down')
SELECT
    g.EVENT_SLUG,
    g.CONDITION_ID,
    g.EVENT_NAME,
    g.EVENT_START_TIME,
    g.END_DATE,
    g.RESULT,
    g.THE_TIME,
    g.SECONDS_TO_END,
    bu.PRICE AS BUY_UP,
    su.PRICE AS SELL_UP,
    bd.PRICE AS BUY_DOWN,
    sd.PRICE AS SELL_DOWN,
    bp.CLOSE AS BITCOIN_PRICE,
    bs.OPEN  AS BTC_START_PRICE
FROM GRID g
ASOF LEFT JOIN BUY_UP    bu ON bu.CONDITION_ID = g.CONDITION_ID AND g.THE_TIME >= bu.TIMESTAMP
ASOF LEFT JOIN SELL_UP   su ON su.CONDITION_ID = g.CONDITION_ID AND g.THE_TIME >= su.TIMESTAMP
ASOF LEFT JOIN BUY_DOWN  bd ON bd.CONDITION_ID = g.CONDITION_ID AND g.THE_TIME >= bd.TIMESTAMP
ASOF LEFT JOIN SELL_DOWN sd ON sd.CONDITION_ID = g.CONDITION_ID AND g.THE_TIME >= sd.TIMESTAMP
LEFT JOIN bitcoin_prices bp ON bp.OPEN_TIME = g.THE_TIME
LEFT JOIN bitcoin_prices bs ON bs.OPEN_TIME = g.EVENT_START_TIME
ORDER BY g.EVENT_SLUG, g.THE_TIME;
