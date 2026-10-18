"""
Inference service (component C): serves predictions and monitoring data
read from Postgres. Does not predict itself -- learn/predict_copy_version.py
already writes every prediction to learn.predictions on its own schedule;
this just makes that data queryable over the internet.

Run:  uv run uvicorn api.main:app --reload
"""
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

load_dotenv()

AREA = os.environ["PRICE_AREA"]
TARGET = os.getenv("TARGET", "mean")

app = FastAPI(title="Elpris Prediction API")


def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def fetch_all(sql: str, params: tuple) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@app.get("/health")
def health():
    """Liveness + a real DB round trip, not just "the process is running"."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:
        raise HTTPException(503, f"database unreachable: {exc}") from exc
    return {"status": "ok", "price_area": AREA, "target": TARGET}


@app.get("/api/latest")
def latest_prediction():
    """The most recently made prediction, resolved or not.

    price_today/tomorrow_temp_mean/tomorrow_wind_mean come straight out of
    feature_snapshot -- the frozen inputs this exact prediction was built
    on -- not a live lookup, so the UI's "vs today" comparison and weather
    context stay correct even after feat__daily moves on.
    """
    rows = fetch_all(
        """
        SELECT target_date, predicted_value, weather_is_forecast,
               model_version, model_revision, predicted_at,
               (feature_snapshot->>'price_today')::numeric AS price_today,
               (feature_snapshot->>'tomorrow_temp_mean')::numeric AS tomorrow_temp_mean,
               (feature_snapshot->>'tomorrow_wind_mean')::numeric AS tomorrow_wind_mean
        FROM learn.predictions
        WHERE price_area = %s AND target = %s
        ORDER BY target_date DESC, predicted_at DESC
        LIMIT 1
        """,
        (AREA, TARGET),
    )
    if not rows:
        raise HTTPException(404, "no predictions yet")
    return rows[0]


@app.get("/api/history")
def history(days: int = 30):
    """Resolved days (predicted vs actual) for the last `days` days, oldest first."""
    rows = fetch_all(
        """
        SELECT target_date, predicted_value, actual_value, error, abs_error,
               weather_is_forecast
        FROM learn.monitor_daily
        WHERE price_area = %s AND target = %s
        ORDER BY target_date DESC
        LIMIT %s
        """,
        (AREA, TARGET, days),
    )
    return list(reversed(rows))


@app.get("/api/monitor/rolling")
def monitor_rolling(days: int = 30):
    """Rolling 7-day/30-day accuracy as a time series, oldest first."""
    rows = fetch_all(
        """
        SELECT target_date, mae_7d, bias_7d, n_days_7d, mae_30d, n_days_30d
        FROM learn.monitor_rolling
        WHERE price_area = %s AND target = %s
        ORDER BY target_date DESC
        LIMIT %s
        """,
        (AREA, TARGET, days),
    )
    return list(reversed(rows))


# Registered last on purpose: explicit routes above always win over this
# mount for the exact paths they match, and everything else falls through
# to the static UI.
app.mount("/", StaticFiles(directory="api/static", html=True), name="static")
