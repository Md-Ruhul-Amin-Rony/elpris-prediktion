-- Bronze layer: raw payloads, append-only, never edited.
CREATE SCHEMA IF NOT EXISTS learn;

CREATE TABLE IF NOT EXISTS learn.raw__elpris (
    raw_id              BIGSERIAL   PRIMARY KEY,
    ingestion_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_area          TEXT        NOT NULL,
    price_date          DATE        NOT NULL,
    data                JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS raw__elpris_key_idx
    ON learn.raw__elpris (price_area, price_date);

CREATE TABLE IF NOT EXISTS learn.raw__weather (
    raw_id              BIGSERIAL   PRIMARY KEY,
    ingestion_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    station             TEXT        NOT NULL,
    parameter           TEXT        NOT NULL,
    observed_at         TIMESTAMPTZ NOT NULL,
    data                JSONB       NOT NULL
);

CREATE INDEX IF NOT EXISTS raw__weather_key_idx
    ON learn.raw__weather (station, parameter, observed_at);
-- Where each weather reading came from. SMHI serves the same hour through
-- two feeds; Silver prefers the quality-controlled archive when both exist.
ALTER TABLE learn.raw__weather
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'latest-months';