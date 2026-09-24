-- Silver layer: one trustworthy, typed row per real-world fact.
-- These are views over Bronze. Nothing is stored, nothing is deleted.
-- Silver makes no judgement calls: no filtering, no interpolation, no clipping.


-- -----------------------------------------------------------------
-- Prices: one row per price interval.
-- Pick the newest whole day from Bronze first, then unpack it.
-- -----------------------------------------------------------------
CREATE OR REPLACE VIEW learn.silver__elpris AS
WITH latest_day AS (
    SELECT DISTINCT ON (price_area, price_date)
           price_area,
           price_date,
           data,
           ingestion_timestamp
    FROM learn.raw__elpris
    ORDER BY price_area, price_date,
             ingestion_timestamp DESC,
             raw_id DESC
)
SELECT
    d.price_area,
    d.price_date,
    (e ->> 'time_start')::timestamptz   AS starts_at,
    (e ->> 'time_end')::timestamptz     AS ends_at,
    (EXTRACT(EPOCH FROM (e ->> 'time_end')::timestamptz
                      - (e ->> 'time_start')::timestamptz) / 60)::int
                                        AS interval_minutes,
    (e ->> 'SEK_per_kWh')::numeric      AS sek_per_kwh,
    (e ->> 'EUR_per_kWh')::numeric      AS eur_per_kwh,
    (e ->> 'EXR')::numeric              AS exchange_rate,
    d.ingestion_timestamp
FROM latest_day AS d
CROSS JOIN LATERAL jsonb_array_elements(d.data) AS e;


-- -----------------------------------------------------------------
-- Weather: one row per station, parameter and hour.
-- Prefer the corrected archive, then the newest fetch.
-- -----------------------------------------------------------------
CREATE OR REPLACE VIEW learn.silver__weather AS
SELECT DISTINCT ON (station, parameter, observed_at)
       station,
       parameter,
       observed_at,
       NULLIF(data ->> 'value', '')::numeric AS value,
       data ->> 'quality'                    AS quality,
       source,
       ingestion_timestamp
FROM learn.raw__weather
ORDER BY station, parameter, observed_at,
         (source = 'corrected-archive') DESC,
         ingestion_timestamp DESC,
         raw_id DESC;