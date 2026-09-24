-- Gold layer: one row per day we want to predict, per price area.
-- Every column here is something we would know at prediction time,
-- except `y`, which is the answer we are trying to learn.

CREATE TABLE IF NOT EXISTS learn.feat__daily (
    price_area          TEXT        NOT NULL,
    target_date         DATE        NOT NULL,   -- the day being predicted

    -- tomorrow's weather: observations today, a forecast in production
    tomorrow_temp_mean  NUMERIC,
    tomorrow_temp_min   NUMERIC,
    tomorrow_temp_max   NUMERIC,
    tomorrow_wind_mean  NUMERIC,

    -- price history known at prediction time
    price_today         NUMERIC,
    price_yesterday     NUMERIC,
    price_7d_ago        NUMERIC,
    price_7d_mean       NUMERIC,
    peak_today          NUMERIC,

    -- calendar facts about target_date itself
    dayofweek           SMALLINT,
    month               SMALLINT,
    is_weekend          BOOLEAN,

    -- how complete the source data was, before any interpolation
    n_intervals         SMALLINT,   -- price intervals on day D
    n_obs_temp          SMALLINT,   -- real temperature readings on D+1
    n_obs_wind          SMALLINT,
    share_quality_g     NUMERIC,    -- share of D+1 readings marked G

    y                   NUMERIC,    -- the true price on target_date

    built_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (price_area, target_date)
);