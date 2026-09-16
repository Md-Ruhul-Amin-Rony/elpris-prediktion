-- GOLD / FEATURE LAYER
-- One row per price area and target day. A row keyed on target_date holds
-- the information known on target_date - 1: that day's prices, the lags and
-- the observed weather on target_date. y is the price on target_date for the
-- assigned target (TARGET=mean today) and is NULL on the newest row.
-- built_at is rewritten on every update by feature_pipeline.py.
-- The columns match FEATURES in model/train.py.
--
-- 2026-09-11: key changed from feature_date to (price_area, target_date),
-- target_price renamed to y, built_at added. The old table was dropped by
-- hand in Neon before this file was applied: DROP TABLE feat__daily;

CREATE TABLE IF NOT EXISTS feat__daily (
    price_area TEXT NOT NULL,
    target_date DATE NOT NULL,

    tomorrow_temp_mean DOUBLE PRECISION,
    tomorrow_temp_min DOUBLE PRECISION,
    tomorrow_temp_max DOUBLE PRECISION,
    tomorrow_wind_mean DOUBLE PRECISION,

    price_today DOUBLE PRECISION,
    price_yesterday DOUBLE PRECISION,
    price_7d_ago DOUBLE PRECISION,
    price_7d_mean DOUBLE PRECISION,
    peak_today DOUBLE PRECISION,

    dayofweek SMALLINT,
    month SMALLINT,
    is_weekend BOOLEAN,

    y DOUBLE PRECISION,

    built_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (price_area, target_date)
);