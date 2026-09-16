
--  SILVER LAYER: ELECTRICITY PRICES

CREATE OR REPLACE VIEW silver__elpris AS
WITH latest AS (
    SELECT DISTINCT ON (price_area, price_date)
           price_area,
           price_date,
           ingestion_timestamp,
           data
    FROM raw__elpris
    ORDER BY price_area, price_date, ingestion_timestamp DESC, raw_id DESC
)
SELECT
    l.price_area,
    l.price_date,
    (e ->> 'time_start')::timestamptz AS starts_at,
    (e ->> 'time_end')::timestamptz   AS ends_at,
    (e ->> 'SEK_per_kWh')::numeric    AS sek_per_kwh,
    (e ->> 'EUR_per_kWh')::numeric    AS eur_per_kwh,
    (e ->> 'EXR')::numeric            AS exr,
    l.ingestion_timestamp
FROM latest AS l,
     LATERAL jsonb_array_elements(l.data) AS e;



--SILVER LAYER: WEATHER OBSERVATIONS
CREATE OR REPLACE VIEW silver__weather AS
SELECT DISTINCT ON (station, parameter, observed_at)
       station,
       parameter,
       observed_at,
       (data ->> 'value')::numeric AS value,
       data ->> 'quality'          AS quality,
       ingestion_timestamp
FROM raw__weather
ORDER BY station, parameter, observed_at, ingestion_timestamp DESC, raw_id DESC;