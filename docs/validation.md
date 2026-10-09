# Validation of the raw layer

## The rule

For every complete local day we count the price intervals in `raw__elpris`
and the hours with a value per weather parameter in `raw__weather`, and
compare with what the day should contain (24 or 96 intervals, 23 to 25
hours), because "did it arrive, and all of it" is the failure that reaches
a model without crashing anything: the missing wind series at station
98230 looked exactly like a normal file until someone counted.

## How it runs

    uv run python validate.py --days 7

Run after the daily ingestion, same window (complete days up to
yesterday). Raw is never touched and nothing is stored: the outcome is a
printed summary, one line per check plus one line per day that differs.
Nothing is rejected: a missing hour is a printed line, not a deleted row
in raw. Duplicates across runs are not a finding; the query picks the
newest ingestion per key, the same rule as the silver views.

Two checks per run: `elpris_intervals` and `weather_hours`. A check is
`ok` when found equals expected, otherwise it prints `MISSING` and the
days that differ. Gaps that persist are written into the table below by
hand; a stored run history was left out on purpose (decision #60).

## Known gaps, station 97400, 2025-09-28 to 2026-09-02

Prices: complete, 32,424 intervals. Weather: 49 of 16,320 hours have no
value (0.3 %), 18 temperature and 31 wind. Hours found per day where
something is missing (24 expected):

| day        | temperature | wind |
|------------|-------------|------|
| 2025-10-15 | 19          | 19   |
| 2025-10-16 | 20          | 20   |
| 2025-10-17 | 24          | 22   |
| 2025-11-25 | 24          | 23   |
| 2025-11-26 | 23          | 23   |
| 2025-12-10 | 23          | 23   |
| 2025-12-11 | 19          | 19   |
| 2026-01-01 | 24          | 23   |
| 2026-01-02 | 24          | 20   |
| 2026-02-11 | 23          | 23   |
| 2026-04-05 | 24          | 23   |
| 2026-06-20 | 24          | 21   |
| 2026-07-10 | 24          | 23   |
| 2026-08-12 | 23          | 23   |

How gaps are handled is decided below; validation only counts them.

## How gaps are handled: bridge short gaps, drop sparse days

Team decision 2026-10-09 (card #36 revisited, supersedes 2026-09-08):
a few missing hours can reasonably be interpolated; a long outage
should not be averaged over as if it were a normal day. The line:

- A run of up to `INTERPOLATE_GAP_HOURS` (3) consecutive missing hours
  is linearly interpolated, on the UTC hourly grid so the gap length
  means the same thing across a DST change.
- A day with more real hours missing than `MAX_MISSING_HOURS_PER_DAY`
  (3) — whether from one longer gap or several short ones — gets a
  null aggregate for that variable (temperature and wind are judged
  independently) instead of a mean computed over mostly-missing hours.
  That null feature row is dropped at training time by the existing
  `FEATURES` dropna in `model/train.py`'s `main()`.

Implemented in `fill_weather_gaps` and `daily_weather_table` in
`model/train.py`, covered by `tests/test_weather_gaps.py`. `n_obs`
(one column) is now `n_obs_temp` and `n_obs_wind` (counts of real,
non-interpolated hours), since a gap in one variable should not drop
the other.

Checked against `silver__weather` for station 97400 on 2026-09-08,
2024-08-01 to 2026-09-07, 768 days:

- no price day lacks weather entirely;
- 8 temperature days and 11 wind days have fewer than 23 hours, the
  shortest has 19 (5 hours missing) — under the old rule these were
  kept with a mean over fewer hours; under this rule a 5-hour day now
  gets a null aggregate and is dropped, since 5 > `MAX_MISSING_HOURS_PER_DAY`;
- 16 wind values are NULL and are skipped the same way a missing hour is;
- every observation carries quality code G.

Revisit the two thresholds if a multi-day outage is ever observed (the
case this rule exists for) or if the drop rate at training time turns
out to matter more than the interpolation does.

## Not flagged, on purpose

- Negative prices: normal in this market when wind is high and demand low.
- SMHI quality code Y (coarser control): kept as information in raw.
- The 23- and 25-hour days at the DST changes: expected, not a gap.
