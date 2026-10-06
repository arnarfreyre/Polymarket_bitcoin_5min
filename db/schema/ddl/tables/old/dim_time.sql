DROP TABLE IF EXISTS dim_time_segments;
CREATE TABLE IF NOT EXISTS dim_time_segments
(
    dt_ID            VARCHAR,
    EVENT_START_TIME TIMESTAMPTZ,
    END_DATE         TIMESTAMPTZ
);
