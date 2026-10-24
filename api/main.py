"""
Inference service (component C): serves predictions and monitoring data
read from Postgres, and can also trigger a fresh on-demand prediction
(POST /api/predict) instead of only ever reading what the daily scheduled
job already wrote.

Run:  uv run uvicorn api.main:app --reload
"""
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

load_dotenv()

# learn/ scripts use bare imports between themselves (e.g. predict_copy_version.py
# does `from train_copy_version import FEATURES`), so they only import cleanly
# if learn/ itself is on sys.path -- same reason pytest needs it in pyproject.toml.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "learn"))
from build_gold_copy_version import refresh_gold  # noqa: E402
from forecast_ingest_copy_version import fetch_and_store_forecast  # noqa: E402
from predict_copy_version import predict_and_log  # noqa: E402

AREA = os.getenv("PRICE_AREA")
STATION = os.getenv("STATION_ID")
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


@app.post("/api/predict")
def predict_now():
    """Refresh the forecast, rebuild Gold, then predict -- all on demand.

    The scheduled daily job only runs this whole chain once a night, so
    feat__daily's weather is frozen between runs even though SMHI reissues
    its forecast several times a day. A click here re-fetches the
    forecast and rebuilds the one affected row before predicting, so the
    result reflects the freshest forecast available right now instead of
    whatever was fetched last night. Safe to call repeatedly:
    monitor_copy_version.py always scores the EARLIEST prediction for a
    day, so an extra manual one never corrupts the accuracy numbers, it
    just adds another row.
    """
    if not AREA or not STATION:
        raise HTTPException(503, "PRICE_AREA and STATION_ID must both be set")
    conn = get_connection()
    try:
        fetch_and_store_forecast(conn, STATION)
        refresh_gold(conn, AREA, STATION, TARGET)
        return predict_and_log(conn, AREA, TARGET)
    except SystemExit as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"prediction failed: {exc}") from exc
    finally:
        conn.close()


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
    """Rolling 7-day/30-day accuracy as a time series, oldest first.

    naive_mae_* is the "tomorrow = today" baseline over the same window --
    card #47's own bar for "is this model actually good" -- so the UI can
    say something honest about performance instead of a bare MAE number
    with no reference point.
    """
    rows = fetch_all(
        """
        SELECT target_date, mae_7d, bias_7d, n_days_7d, mae_30d, n_days_30d,
               naive_mae_7d, naive_mae_30d
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
