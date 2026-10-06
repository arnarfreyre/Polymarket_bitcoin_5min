
DROP VIEW IF EXISTS trader_stats_v;

-- One row per wallet. Reads the positions table (positions_v materialized).
-- OVERSOLD_MARKETS = markets where the wallet sold more shares than it bought (maker fills are missing).
CREATE OR REPLACE VIEW trader_stats_v AS

SELECT
    PROXY_WALLET,
    any_value(NAME) AS NAME,
    sum(N_TRADES) AS N_TRADES,
    count(*) AS N_MARKETS,
    sum(BUY_USD) AS BUY_USD,
    sum(SELL_USD) AS SELL_USD,
    sum(PNL) AS PNL,
    sum(PNL) / nullif(sum(BUY_USD), 0) AS ROI,
    count(*) FILTER (WHERE PNL > 0) AS MARKETS_WON,
    count(*) FILTER (WHERE PNL < 0) AS MARKETS_LOST,
    count(*) FILTER (WHERE NET_UP_SHARES < -0.01 OR NET_DOWN_SHARES < -0.01) AS OVERSOLD_MARKETS,
    min(FIRST_TIME) AS FIRST_TIME,
    max(LAST_TIME) AS LAST_TIME
FROM positions
GROUP BY PROXY_WALLET;
