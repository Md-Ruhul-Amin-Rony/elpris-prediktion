"""Hand-built cases for weather gap handling. No database."""

import pandas as pd

from model.train import daily_weather_table


def hourly_frame(hours: int = 24) -> pd.DataFrame:
    """One continuous local day (2026-01-01, Stockholm) with no gaps."""
    idx = pd.date_range("2025-12-31 23:00", periods=hours, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "ts_utc": idx,
            "temp_c": list(range(hours)),
            "wind_ms": [1.0] * hours,
        }
    )


def test_full_day_has_no_missing_hours():
    df = hourly_frame()
    daily = daily_weather_table(df)
    assert daily.loc["2026-01-01", "n_obs_temp"] == 24
    assert daily["temp_mean"].notna().all()


def test_short_gap_is_interpolated_and_day_stays_usable():
    df = hourly_frame()
    # A 2-hour gap, <= INTERPOLATE_GAP_HOURS: bridged, day still usable.
    df.loc[[5, 6], "temp_c"] = None

    daily = daily_weather_table(df)
    row = daily.loc["2026-01-01"]

    assert row["n_obs_temp"] == 22
    assert pd.notna(row["temp_mean"])


def test_long_gap_leaves_aggregate_null():
    df = hourly_frame()
    # A 6-hour gap, > MAX_MISSING_HOURS_PER_DAY: left null, not averaged over.
    df.loc[5:10, "temp_c"] = None

    daily = daily_weather_table(df)
    row = daily.loc["2026-01-01"]

    assert row["n_obs_temp"] == 18
    assert pd.isna(row["temp_mean"])
    assert pd.isna(row["temp_min"])
    assert pd.isna(row["temp_max"])


def test_gap_in_one_variable_does_not_affect_the_other():
    df = hourly_frame()
    df.loc[5:10, "temp_c"] = None  # temperature: long gap, dropped

    daily = daily_weather_table(df)
    row = daily.loc["2026-01-01"]

    assert pd.isna(row["temp_mean"])
    assert row["wind_mean"] == 1.0  # wind: no gap, unaffected
