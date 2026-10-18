-- Daily monitor: one row per resolved prediction day, upserted once the
-- real price is known (feat__daily.y is no longer NULL for that day).
-- Scored against the EARLIEST prediction made for that day -- later
-- same-day re-predictions had more information available and are not a
-- fair test of forecast skill.

CREATE TABLE IF NOT EXISTS learn.monitor_daily (
    price_area           TEXT NOT NULL,
    target_date          DATE NOT NULL,
    target                TEXT NOT NULL,

    prediction_id           BIGINT NOT NULL REFERENCES learn.predictions(id),
    predicted_value         NUMERIC NOT NULL,
    actual_value             NUMERIC NOT NULL,
    error                    NUMERIC NOT NULL,       -- predicted - actual: signed, shows bias
    abs_error                NUMERIC NOT NULL,
    weather_is_forecast      BOOLEAN NOT NULL,

    resolved_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (price_area, target_date, target)
);

-- Rolling view: a time series of 7-day and 30-day rolling accuracy, not a
-- single static number -- so a dashboard can plot how real-world accuracy
-- drifts over time. n_days_* is exposed so an early, thin window (e.g. only
-- 3 days of history so far) doesn't get mistaken for a stable 7-day figure.
CREATE OR REPLACE VIEW learn.monitor_rolling AS
SELECT
    price_area,
    target_date,
    target,
    predicted_value,
    actual_value,
    error,
    abs_error,
    weather_is_forecast,
    COUNT(*) OVER (
        PARTITION BY price_area, target ORDER BY target_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS n_days_7d,
    AVG(abs_error) OVER (
        PARTITION BY price_area, target ORDER BY target_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS mae_7d,
    AVG(error) OVER (
        PARTITION BY price_area, target ORDER BY target_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS bias_7d,
    COUNT(*) OVER (
        PARTITION BY price_area, target ORDER BY target_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS n_days_30d,
    AVG(abs_error) OVER (
        PARTITION BY price_area, target ORDER BY target_date
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS mae_30d
FROM learn.monitor_daily
ORDER BY target_date;
