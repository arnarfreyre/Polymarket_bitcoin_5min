
DROP VIEW IF EXISTS positions_v;

-- One row per (wallet, market). Filter on PROXY_WALLET (indexed) or CONDITION_ID so lookups stay fast.
-- EVENT_SLUG comes from the markets table: a few trades have an empty EVENT_SLUG.
-- PNL = sell proceeds - buy cost + net shares of the winning outcome * $1 (taker trades only).
CREATE OR REPLACE VIEW positions_v AS
SELECT
    t.PROXY_WALLET,
    t.CONDITION_ID,
    m.EVENT_SLUG,
    any_value(nullif(t.NAME, '')) AS NAME,
    count(*) AS N_TRADES,
    coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'BUY'), 0) AS BUY_USD,
    coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'SELL'), 0) AS SELL_USD,
    coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'BUY' AND t.OUTCOME = 'Up'), 0) AS BUY_UP_USD,
    coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'BUY' AND t.OUTCOME = 'Down'), 0) AS BUY_DOWN_USD,
    coalesce(sum(t.SIZE) FILTER (WHERE t.SIDE = 'BUY'), 0) AS BUY_SHARES,
    coalesce(sum(CASE WHEN t.SIDE = 'BUY' THEN t.SIZE ELSE -t.SIZE END) FILTER (WHERE t.OUTCOME = 'Up'), 0) AS NET_UP_SHARES,
    coalesce(sum(CASE WHEN t.SIDE = 'BUY' THEN t.SIZE ELSE -t.SIZE END) FILTER (WHERE t.OUTCOME = 'Down'), 0) AS NET_DOWN_SHARES,
    coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'SELL'), 0)
      - coalesce(sum(t.SIZE * t.PRICE) FILTER (WHERE t.SIDE = 'BUY'), 0)
      + coalesce(sum(CASE WHEN t.SIDE = 'BUY' THEN t.SIZE ELSE -t.SIZE END) FILTER (WHERE t.OUTCOME = m.RESULT), 0) AS PNL,
    min(t.TIMESTAMP) AS FIRST_TIME,
    max(t.TIMESTAMP) AS LAST_TIME
FROM bitcoin_5m_trades t
JOIN bitcoin_5m_markets m USING (CONDITION_ID)
GROUP BY t.PROXY_WALLET, t.CONDITION_ID, m.EVENT_SLUG;
