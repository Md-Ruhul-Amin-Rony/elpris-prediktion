-- Forecast staging: SMHI's point-forecast values, kept append-only.
--
-- Unlike raw__weather (an observation, settled once the hour happens),
-- a forecast for the same valid_at changes every time SMHI reissues it.
-- Overwriting would throw away exactly the history needed to one day
-- measure real forecast error (see learn/train_copy_version.py's
-- FORECAST_ERROR_C, currently a guess) -- so every fetch is a new row,
-- keyed by (station, parameter, valid_at, issued_at).

CREATE TABLE IF NOT EXISTS learn.stg__forecast (
    raw_id              BIGSERIAL   PRIMARY KEY,
    ingestion_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    station             TEXT        NOT NULL,   -- same station id as raw__weather
    parameter           TEXT        NOT NULL,   -- 'temperature' or 'wind', same naming as raw__weather
    issued_at           TIMESTAMPTZ NOT NULL,   -- SMHI's referenceTime: when this forecast run was made
    valid_at            TIMESTAMPTZ NOT NULL,   -- the hour this value forecasts
    data                JSONB       NOT NULL    -- the untouched SMHI timeSeries entry
);

CREATE INDEX IF NOT EXISTS stg__forecast_key_idx
    ON learn.stg__forecast (station, parameter, valid_at, issued_at DESC);


-- Silver: one row per station, parameter and forecast hour -- same long
-- shape as silver__weather. "Latest wins" here means most recently
-- *issued*, not most recently ingested: a forecast issued later for the
-- same hour is generally the more accurate one.
CREATE OR REPLACE VIEW learn.silver__forecast AS
SELECT DISTINCT ON (station, parameter, valid_at)
       station,
       parameter,
       valid_at,
       issued_at,
       CASE parameter
           WHEN 'temperature' THEN (data -> 'data' ->> 'air_temperature')::numeric
           WHEN 'wind'        THEN (data -> 'data' ->> 'wind_speed')::numeric
       END AS value,
       ingestion_timestamp
FROM learn.stg__forecast
ORDER BY station, parameter, valid_at, issued_at DESC, ingestion_timestamp DESC;
