"""
Resolve predictions against real outcomes into learn.monitor_daily.

A target_date is resolved once feat__daily.y is known for it. Scores the
EARLIEST prediction made for that day: later same-day re-predictions had
more information available and are not a fair test of forecast skill.
Idempotent -- safe to run every day regardless of what is newly resolved.

Run:  uv run python learn/monitor_copy_version.py
"""
import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# os.getenv, not os.environ[...]: consistent with the other learn/ scripts
# that got imported elsewhere -- this one isn't imported anywhere yet, but
# there's no reason to leave the same trap lying around for later.
AREA = os.getenv("PRICE_AREA")

UPSERT_SQL = """
    INSERT INTO learn.monitor_daily (
        price_area, target_date, target,
        prediction_id, predicted_value, actual_value,
        error, abs_error, weather_is_forecast,
        naive_value, naive_abs_error
    )
    SELECT
        p.price_area, p.target_date, p.target,
        p.id, p.predicted_value, f.y,
        p.predicted_value - f.y, abs(p.predicted_value - f.y),
        p.weather_is_forecast,
        (p.feature_snapshot->>'price_today')::numeric,
        abs((p.feature_snapshot->>'price_today')::numeric - f.y)
    FROM learn.predictions p
    JOIN learn.feat__daily f
      ON f.price_area = p.price_area AND f.target_date = p.target_date
    JOIN (
        SELECT price_area, target_date, target, MIN(predicted_at) AS first_at
        FROM learn.predictions
        GROUP BY price_area, target_date, target
    ) earliest
      ON earliest.price_area = p.price_area
     AND earliest.target_date = p.target_date
     AND earliest.target = p.target
     AND earliest.first_at = p.predicted_at
    WHERE p.price_area = %s AND f.y IS NOT NULL
    ON CONFLICT (price_area, target_date, target) DO UPDATE SET
        prediction_id = EXCLUDED.prediction_id,
        predicted_value = EXCLUDED.predicted_value,
        actual_value = EXCLUDED.actual_value,
        error = EXCLUDED.error,
        abs_error = EXCLUDED.abs_error,
        weather_is_forecast = EXCLUDED.weather_is_forecast,
        naive_value = EXCLUDED.naive_value,
        naive_abs_error = EXCLUDED.naive_abs_error,
        resolved_at = now()
"""


def main() -> None:
    if not AREA:
        raise SystemExit("PRICE_AREA is not set.")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn, conn.cursor() as cur:
            cur.execute(UPSERT_SQL, (AREA,))
            print(f"monitor: resolved/refreshed {cur.rowcount} day(s)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
