
DROP VIEW IF EXISTS market_stats_v;

-- One row per market (markets without trades included). Reads the positions table (positions_v materialized).
CREATE OR REPLACE VIEW market_stats_v AS

SELECT
    m.CONDITION_ID,
    m.EVENT_SLUG,
    m.QUESTION,
    replace(m.QUESTION, 'Bitcoin Up or Down - ', '') AS LABEL,
    m.EVENT_START_TIME,
    m.END_DATE,
    m.RESULT,
    coalesce(p.N_TRADES, 0) AS N_TRADES,
    coalesce(p.N_TRADERS, 0) AS N_TRADERS,
    coalesce(p.VOLUME_USD, 0) AS VOLUME_USD,
    p.N_WINNERS,
    p.N_LOSERS,
    p.WINNERS_PNL,
    p.LOSERS_PNL,
    p.NET_PNL,
    p.NET_PNL / nullif(p.N_TRADERS, 0) AS AVG_PNL
FROM bitcoin_5m_markets m
LEFT JOIN (
    SELECT
        CONDITION_ID,
        sum(N_TRADES) AS N_TRADES,
        count(*) AS N_TRADERS,
        sum(BUY_USD + SELL_USD) AS VOLUME_USD,
        count(*) FILTER (WHERE PNL > 0) AS N_WINNERS,
        count(*) FILTER (WHERE PNL < 0) AS N_LOSERS,
        sum(PNL) FILTER (WHERE PNL > 0) AS WINNERS_PNL,
        sum(PNL) FILTER (WHERE PNL < 0) AS LOSERS_PNL,
        sum(PNL) AS NET_PNL
    FROM positions
    GROUP BY CONDITION_ID
) p USING (CONDITION_ID);
