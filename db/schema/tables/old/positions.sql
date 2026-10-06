-- positions_v materialized; see db/schema/views/positions.sql for the PnL logic.
INSERT INTO positions
SELECT * FROM positions_v
ORDER BY PROXY_WALLET, EVENT_SLUG;
