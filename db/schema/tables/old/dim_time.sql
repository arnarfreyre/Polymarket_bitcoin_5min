INSERT INTO dim_time_segments
SELECT
    m.MARKET_ID AS dt_ID,
    m.EVENT_START_TIME,
    m.END_DATE
FROM bitcoin_5m_markets m;
