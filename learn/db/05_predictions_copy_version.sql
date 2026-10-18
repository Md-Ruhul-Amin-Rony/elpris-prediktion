-- Prediction log: one row per inference run, never updated or deleted.
-- Component D: which data (feature_snapshot), which code (git_sha), which
-- model (model_version/model_revision), and when (predicted_at).

CREATE TABLE IF NOT EXISTS learn.predictions (
    id                   BIGSERIAL PRIMARY KEY,
    price_area           TEXT NOT NULL,
    target_date          DATE NOT NULL,
    target               TEXT NOT NULL,              -- 'mean' or 'peak'

    predicted_value      NUMERIC NOT NULL,

    -- which data: a snapshot, not a pointer. feat__daily is overwritten
    -- nightly (forecast weather becomes real observed weather once the
    -- day passes), so the row used right now will not look like this later.
    feature_snapshot     JSONB NOT NULL,
    weather_is_forecast  BOOLEAN NOT NULL,
    feature_built_at     TIMESTAMPTZ NOT NULL,       -- feat__daily.built_at for that row

    -- which model and which code
    model_version        TEXT NOT NULL,              -- e.g. SE3-mean-20261018-1235-95fca22
    feature_version      TEXT NOT NULL,
    model_revision        TEXT NOT NULL,              -- Hugging Face Hub commit sha of the champion used
    git_sha                TEXT NOT NULL,              -- commit the champion was TRAINED at

    predicted_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS predictions_lookup_idx
    ON learn.predictions (price_area, target_date, target);
