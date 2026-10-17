"""Hand-built cases for feature engineering. No database."""

import pandas as pd
from features_copy_version import (
    build_features,
    daily_forecast,
    daily_prices,
    daily_weather,
    fill_forecast_gaps,
)


def hourly_index(first_utc_hour):
    """24 hourly UTC timestamps making up one full Swedish local day."""
    return pd.date_range(first_utc_hour, periods=24, freq="h", tz="UTC")


def test_daily_prices_aggregates_one_day():
    prices = pd.DataFrame({
        "starts_at": [
            "2026-01-15T00:00:00+01:00",
            "2026-01-15T12:00:00+01:00",
        ],
        "sek_per_kwh": [1.0, 3.0],
    })
    daily = daily_prices(prices)
    row = daily.loc["2026-01-15"]
    assert (row["mean_price"], row["peak_price"], row["n_intervals"]) == (2.0, 3.0, 2)


def test_daily_weather_full_day_no_gap():
    idx = hourly_index("2026-01-14 23:00")  # -> local 2026-01-15, winter, no DST
    weather = pd.DataFrame({
        "observed_at": list(idx) * 2,
        "parameter": ["temperature"] * 24 + ["wind"] * 24,
        "value": list(range(24)) + [1.0] * 24,
        "quality": ["G"] * 48,
    })
    daily = daily_weather(weather)
    row = daily.loc["2026-01-15"]
    assert row["temp_mean"] == 11.5
    assert row["temp_min"] == 0.0
    assert row["temp_max"] == 23.0
    assert row["n_obs_temp"] == 24
    assert row["n_obs_wind"] == 24
    assert row["share_quality_g"] == 1.0


def test_daily_weather_short_gap_is_interpolated_but_not_counted_as_observed():
    idx = hourly_index("2026-01-14 23:00")
    temp = list(range(24))
    for hour in (10, 11, 12):  # 3-hour gap, <= MAX_GAP_HOURS (6): bridged
        temp[hour] = None
    weather = pd.DataFrame({
        "observed_at": list(idx) * 2,
        "parameter": ["temperature"] * 24 + ["wind"] * 24,
        "value": temp + [1.0] * 24,
        "quality": ["G"] * 48,
    })
    daily = daily_weather(weather)
    row = daily.loc["2026-01-15"]
    assert pd.notna(row["temp_mean"])  # interpolation kept the mean computable
    assert row["n_obs_temp"] == 21     # but the 3 interpolated hours are not "real"


def test_build_features_shifts_tomorrow_and_relabels_to_target_date():
    prices = pd.DataFrame({
        "starts_at": [
            f"2026-01-{day:02d}T{hour:02d}:00:00+01:00"
            for day in (14, 15, 16) for hour in range(24)
        ],
        "sek_per_kwh": [1.0, 2.0] * 36,
    })
    daily_price = daily_prices(prices)

    weather = pd.DataFrame(
        {
            "temp_mean": [5.0, 6.0, 7.0],
            "temp_min": [1.0, 2.0, 3.0],
            "temp_max": [9.0, 10.0, 11.0],
            "wind_mean": [2.0, 3.0, 4.0],
            "n_obs_temp": [24, 24, 24],
            "n_obs_wind": [24, 24, 24],
            "share_quality_g": [1.0, 1.0, 1.0],
        },
        index=pd.to_datetime(["2026-01-14", "2026-01-15", "2026-01-16"]),
    )

    feat = build_features(daily_price, weather, target="mean")

    # target_date = Jan 15's row holds Jan 15's OWN weather, not Jan 16's.
    assert feat.loc["2026-01-15", "tomorrow_temp_mean"] == 6.0
    assert feat.loc["2026-01-15", "y"] == 1.5

    # The newest row (Jan 17) has no observed "tomorrow" yet: both NaN.
    assert pd.isna(feat.loc["2026-01-17", "tomorrow_temp_mean"])
    assert pd.isna(feat.loc["2026-01-17", "y"])


def test_daily_forecast_aggregates_one_day():
    idx = hourly_index("2026-01-16 23:00")
    forecast = pd.DataFrame({
        "valid_at": list(idx) * 2,
        "parameter": ["temperature"] * 24 + ["wind"] * 24,
        "value": list(range(24)) + [3.0] * 24,
    })
    daily = daily_forecast(forecast)
    row = daily.loc["2026-01-17"]
    assert (row["temp_mean"], row["temp_min"], row["temp_max"], row["wind_mean"]) == (
        11.5, 0.0, 23.0, 3.0,
    )


def _feat_with_one_unobserved_row():
    """Two historical rows (real weather) plus one newest row with no weather yet."""
    index = pd.to_datetime(["2026-01-15", "2026-01-16", "2026-01-17"])
    return pd.DataFrame(
        {
            "tomorrow_temp_mean": [6.0, 7.0, None],
            "tomorrow_temp_min": [2.0, 3.0, None],
            "tomorrow_temp_max": [10.0, 11.0, None],
            "tomorrow_wind_mean": [3.0, 4.0, None],
            "n_obs_temp": [24, 24, None],
            "n_obs_wind": [24, 24, None],
            "y": [1.5, 1.5, None],
        },
        index=index,
    )


def test_fill_forecast_gaps_fills_only_the_newest_row():
    feat = _feat_with_one_unobserved_row()
    idx = hourly_index("2026-01-16 23:00")  # covers 2026-01-17
    forecast = pd.DataFrame({
        "valid_at": list(idx) * 2,
        "parameter": ["temperature"] * 24 + ["wind"] * 24,
        "value": list(range(24)) + [9.0] * 24,
    })

    filled, n_filled = fill_forecast_gaps(feat, forecast)

    assert n_filled == 4
    # Historical rows: untouched.
    assert filled.loc["2026-01-15", "tomorrow_temp_mean"] == 6.0
    assert filled.loc["2026-01-15", "n_obs_temp"] == 24
    # Newest row: weather filled from forecast...
    assert filled.loc["2026-01-17", "tomorrow_temp_mean"] == 11.5
    assert filled.loc["2026-01-17", "tomorrow_wind_mean"] == 9.0
    # ...n_obs becomes a known 0, not an unknown NaN...
    assert filled.loc["2026-01-17", "n_obs_temp"] == 0
    assert filled.loc["2026-01-17", "n_obs_wind"] == 0
    # ...and y is never forecast-filled: the price is the answer, not an input.
    assert pd.isna(filled.loc["2026-01-17", "y"])


def test_fill_forecast_gaps_with_no_forecast_changes_nothing():
    feat = _feat_with_one_unobserved_row()
    empty_forecast = pd.DataFrame(columns=["valid_at", "parameter", "value"])
    filled, n_filled = fill_forecast_gaps(feat, empty_forecast)
    assert n_filled == 0
    assert pd.isna(filled.loc["2026-01-17", "tomorrow_temp_mean"])
