# Elpris SE3 — day-ahead price prediction

A solo rebuild of a course starter repo (YH-02032, *Data engineering och
Agila metoder*) into a working, automated, end-to-end pipeline: ingest real
weather and electricity-price data, engineer features — including a live
weather forecast for the one day that hasn't happened yet — train and
register a model on Hugging Face Hub, predict daily, and monitor real
accuracy over time, with a small FastAPI service and dashboard to see all
of it.

**Live dashboard: https://el-price-prediction.onrender.com** (hosted on
Render's free tier, so the first request after ~15 idle minutes takes
30–60 s while the service wakes up).

**Everything active lives under `learn/` and `api/`.** `model/` and most of
`docs/` are the original starter repo, kept for reference — see
[What's here from the original starter repo](#whats-here-from-the-original-starter-repo).

## Architecture

```
SMHI (weather) ──┐
                  ├──▶ raw__weather / raw__elpris      Bronze: untouched, append-only
elprisetjustnu ───┘            │
                          silver__weather / silver__elpris   Silver: deduped, typed views
                                │
SMHI forecast ───▶ stg__forecast ──▶ silver__forecast        │
                                │                             │
                                └──────────────┬──────────────┘
                                                ▼
                                        feat__daily        Gold: one row per day to predict
                                                │
                                  ┌─────────────┴──────────────┐
                                  ▼                             ▼
                    train_copy_version.py              predict_copy_version.py
                    weekly, champion/challenger          daily, from the champion
                                  │                             │
                                  ▼                             ▼
                    Hugging Face Hub model repo          learn.predictions      Component D: traceability
                                                                  │
                                                                  ▼
                                                   monitor_daily / monitor_rolling   Component E: monitoring
                                                                  │
                                                                  ▼
                                                        FastAPI (api/) + dashboard
```

## Why a weather forecast at all?

The newest row in `feat__daily` — the only one actually worth predicting —
can never have *observed* weather for its own day, because that day hasn't
happened yet. `learn/forecast_ingest_copy_version.py` fetches SMHI's point
forecast, and `fill_forecast_gaps()` in `features_copy_version.py` fills in
only the cells that are genuinely missing — it never overwrites a real
observation. The full reasoning (and the training/serving skew this
creates, and how `train_copy_version.py` excludes forecast-based rows from
training) is in `docs/validation.md`.

## Quickstart

```bash
cp .env.example .env     # fill in PRICE_AREA, STATION_ID, DATABASE_URL, HF_TOKEN, HF_MODEL_REPO
uv sync --extra dev --extra api
```

Add `--extra notebook` if you want to run `model/utforskning.ipynb` —
that extra is the only place `matplotlib` and `duckdb` live, since nothing
in the pipeline or the API uses them.

Apply the schema once, in order, against your own Postgres (Supabase/Neon
both work) — six small files, run each one in your DB's SQL console or via
`psql`:

```
learn/db/01_bronze_copy_version.sql
learn/db/02_silver_copy_version.sql
learn/db/03_gold_copy_version.sql
learn/db/04_forecast_copy_version.sql
learn/db/05_predictions_copy_version.sql
learn/db/06_monitor_copy_version.sql
```

Then, once, backfill history:

```bash
uv run python learn/backfill_prices_copy_version.py 2024-08-01 2026-10-01
uv run python learn/weather_backfill_copy_version.py 2024-08-01
```

From there the daily and weekly workflows below take over.

## The daily pipeline

Automated: `.github/workflows/learn_daily_pipeline.yml`, 22:00 UTC and on
manual dispatch. In order:

1. **`ingest_copy_version.py`** — today's weather and the latest published prices
2. **`forecast_ingest_copy_version.py`** — SMHI's forecast for the next few days
3. **`validate_copy_version.py`** — checks Silver against the calendar; fails the run if the last 2 days don't look right, so a bad run never silently feeds the next step
4. **`build_gold_copy_version.py`** — rebuilds `feat__daily`, filling the one unresolved row's weather from the forecast
5. **`predict_copy_version.py`** — downloads the current champion model, predicts the still-unresolved day, logs it with full traceability
6. **`monitor_copy_version.py`** — resolves any predictions whose real price is now known

## The weekly training pipeline

Automated: `.github/workflows/learn_train_pipeline.yml`, Sunday 23:30 UTC.
`train_copy_version.py` trains a fresh `HistGradientBoostingRegressor`,
re-scores the *current* Hugging Face champion on this run's own test set —
not a stale number from whenever it was last trained — and only promotes
the new model if it beats **both** the naive baseline and the champion. A
tie doesn't promote; there's no reason to replace a working champion with
an identical one.

## Component D — traceability

Every row in `learn.predictions` answers, permanently: which data
(`feature_snapshot`, frozen at prediction time — `feat__daily` gets
overwritten nightly, so a live pointer would stop being true within a
day), which model (`model_version`, `model_revision` — the exact Hugging
Face commit used), which code (`git_sha` — the commit the champion was
*trained* at), and when (`predicted_at`).

## Component E — monitoring

`learn.monitor_daily` resolves each prediction against its real outcome
once known, scored against the **earliest** prediction made for that day
— a later same-day re-prediction had more information available and
isn't a fair test of forecast skill. `learn.monitor_rolling` turns that
into a 7-day/30-day rolling MAE and bias time series, with the day-count
behind each window exposed so an early, thin window is never mistaken for
a stable figure.

Each resolved day also stores what the naive "tomorrow = today" baseline
would have predicted (`naive_value`, from the prediction's own frozen
`feature_snapshot`), and the rolling view carries `naive_mae_7d`/`_30d`.
That's what the dashboard's verdict ("beating / behind the naive baseline
by N%") is built on — the same bar training uses to decide whether a
model is good. A percent-of-actual "accuracy" figure was considered and
rejected: SE3 prices go to zero or below often enough (over 1,300
intervals in the history) that dividing an error by the actual price
gives meaningless numbers.

## The API and dashboard

```bash
uv run uvicorn api.main:app --reload
```

| Endpoint | What it does |
|---|---|
| `GET /health` | liveness plus a real database round trip |
| `GET /api/latest` | the most recently logged prediction, with today's price and the forecast weather it was built on |
| `POST /api/predict` | on demand: re-fetches the SMHI forecast, rebuilds the affected `feat__daily` row, then predicts and logs it — so it reflects the freshest forecast, not last night's |
| `GET /api/history` | resolved days, predicted vs. actual |
| `GET /api/monitor/rolling` | rolling MAE, bias and the naive-baseline MAE |

`/` serves the dashboard — one static HTML file, no frontend build. The
prediction stays hidden until you click **Show predicted price**; after
that, **Predict again** calls `POST /api/predict`. Each click writes a real
row to `learn.predictions`, which is safe for the accuracy numbers because
monitoring always scores the *earliest* prediction for a day.

## Running in Docker

```bash
docker build -t elpris-api .
docker run --rm -p 8000:8000 --env-file .env elpris-api
```

Then open http://localhost:8000. The image runs only the API and
dashboard — the pipeline and training stay on GitHub Actions. `.env` is
excluded by `.dockerignore`, so secrets are passed at run time, never
baked into the image. The container listens on `$PORT` (default 8000),
which is what Render and Cloud Run both set, and runs as a non-root user.

## Deployment (Render)

Deployed as a Render **Web Service** from this repo's `main` branch, using
Render's native Python runtime (the `Dockerfile` is there for Docker-based
hosts, but Render doesn't need it):

- **Build command:** `pip install -e ".[api]"`
- **Start command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- **Environment variables:** `DATABASE_URL`, `PRICE_AREA`, `STATION_ID`,
  `TARGET`, `HF_TOKEN`, `HF_MODEL_REPO` — the same values as `.env`, set
  in Render's dashboard rather than committed anywhere.

## Testing

```bash
uv run pytest
uv run ruff check .
```

Pure-function logic — calendar math, feature aggregation, the forecast
fill, the prediction-snapshot logic — is covered in `tests/`. Anything
that's mostly a database round trip (`monitor_copy_version.py`'s single
SQL statement, the ingestion scripts) is instead verified by hand against
the real database rather than mocked; see commit history for how.



## Known limitations / next steps

- **Single price area, with two hardcoded assumptions.**
  `forecast_ingest_copy_version.py`'s `STATION_COORDS` only has
  coordinates for station 97400, and `train_copy_version.py` never checks
  that `STATION_ID` actually matches the station `AREA_STATIONS[PRICE_AREA]`
  expects. Changing `PRICE_AREA` without fixing both is a **silent**
  correctness bug, not a crash.
- **One Hugging Face repo, not one per area.** `HF_MODEL_REPO` isn't
  area-specific — switching `PRICE_AREA` without also switching the
  registry would compare a new model against a champion trained for a
  different market, silently.
- **The dashboard isn't read-only.** `POST /api/predict` writes to the
  database and calls SMHI and Hugging Face on every click, with no
  authentication or rate limit. Fine for a personal demo; it would need
  both before being shared widely.
- **Free-tier cold starts** on Render, as noted at the top.
- **Orchestration**: planned move to Airflow for the scheduling currently
  done via GitHub Actions cron — once the pipeline logic stops changing,
  so the migration is a straight swap of scheduler rather than two moving
  parts at once.
