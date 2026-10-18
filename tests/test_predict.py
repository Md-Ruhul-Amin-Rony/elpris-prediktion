"""Hand-built cases for the pure parts of prediction logging. No database.

load_champion/load_unresolved_row do real I/O (Hugging Face, Postgres) and
are not covered here -- they were verified by hand against the real
database and the real Hugging Face repo. Only the pure decision logic
that main() uses is tested.
"""

import pandas as pd
from predict_copy_version import build_feature_snapshot, is_weather_forecast


def test_weather_is_forecast_when_temp_has_zero_real_hours():
    row = pd.Series({"n_obs_temp": 0, "n_obs_wind": 24})
    assert is_weather_forecast(row) is True


def test_weather_is_forecast_when_wind_has_zero_real_hours():
    row = pd.Series({"n_obs_temp": 24, "n_obs_wind": 0})
    assert is_weather_forecast(row) is True


def test_weather_is_not_forecast_when_both_fully_observed():
    row = pd.Series({"n_obs_temp": 24, "n_obs_wind": 24})
    assert is_weather_forecast(row) is False


def test_weather_is_not_forecast_for_a_partial_but_real_day():
    # Today's own row, part-way through the day: real but incomplete.
    row = pd.Series({"n_obs_temp": 11, "n_obs_wind": 11})
    assert is_weather_forecast(row) is False


def test_feature_snapshot_keeps_only_the_requested_columns():
    row = pd.Series({"a": 1.0, "b": 2.0, "c": 3.0})
    snapshot = build_feature_snapshot(row, ["a", "c"])
    assert snapshot == {"a": 1.0, "c": 3.0}


def test_feature_snapshot_turns_nan_into_none_for_json():
    row = pd.Series({"a": float("nan")})
    snapshot = build_feature_snapshot(row, ["a"])
    assert snapshot == {"a": None}
