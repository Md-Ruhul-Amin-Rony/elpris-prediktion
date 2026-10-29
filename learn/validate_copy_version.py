"""
Validation: compare what Silver holds with what the calendar says it should hold.

Reports problems. Never changes data.
Exits with code 1 if something needs attention now, 0 otherwise.

What fails the run, in the last RECENT_DAYS complete days:
  - any missing price interval (prices are never filled in)
  - a weather gap longer than MAX_GAP_HOURS (longer than the features can fill)
  - duplicates, on any day
Shorter weather gaps are filled by the feature step, so they only warn.

Run:  uv run python learn/validate_copy_version.py 2024-08-01
"""
import os
import sys
from datetime import UTC, date, datetime, timedelta

import psycopg2
from dotenv import load_dotenv
from features_copy_version import MAX_GAP_HOURS
from swedish_time_copy_version import (
    STOCKHOLM,
    expected_price_intervals,
    expected_weather_readings,
    local_midnight,
)

load_dotenv()

AREA = os.environ["PRICE_AREA"]
STATION = os.environ["STATION_ID"]
RECENT_DAYS = 2   # problems in the last N complete days fail the run

WEATHER_RANGE = {"temperature": (-45, 40), "wind": (0, 50)}
PRICE_RANGE = (-5, 30)


def all_days(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def longest_gap(day, present):
    """Most consecutive missing hours in one Swedish day."""
    hour = local_midnight(day).astimezone(UTC)
    day_end = local_midnight(day + timedelta(days=1)).astimezone(UTC)
    longest = run = 0
    while hour < day_end:
        run = 0 if hour in present else run + 1
        longest = max(longest, run)
        hour += timedelta(hours=1)
    return longest


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: validate_copy_version.py <first-date YYYY-MM-DD>")

    start = date.fromisoformat(sys.argv[1])
    end = datetime.now(STOCKHOLM).date() - timedelta(days=1)   # last complete day
    recent_from = end - timedelta(days=RECENT_DAYS - 1)
    days = list(all_days(start, end))

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:

            # --- what is actually there ---------------------------------
            cur.execute(
                "SELECT price_date, count(*) FROM learn.silver__elpris"
                " WHERE price_area = %s GROUP BY price_date",
                (AREA,),
            )
            price_counts = dict(cur.fetchall())

            cur.execute(
                "SELECT parameter,"
                "       (observed_at AT TIME ZONE 'Europe/Stockholm')::date,"
                "       count(*)"
                " FROM learn.silver__weather WHERE station = %s"
                " GROUP BY 1, 2",
                (STATION,),
            )
            weather_counts = {(p, d): n for p, d, n in cur.fetchall()}

            # The exact hours of the recent days, to measure gap lengths.
            cur.execute(
                "SELECT parameter, observed_at FROM learn.silver__weather"
                " WHERE station = %s AND observed_at >= %s AND observed_at < %s",
                (STATION, local_midnight(recent_from),
                 local_midnight(end + timedelta(days=1))),
            )
            recent_hours = {}
            for name, observed_at in cur.fetchall():
                recent_hours.setdefault(name, set()).add(observed_at)

            # --- structure: must never break ----------------------------
            cur.execute(
                "SELECT count(*) - count(DISTINCT (price_area, starts_at))"
                " FROM learn.silver__elpris"
            )
            price_dupes = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) - count(DISTINCT (station, parameter, observed_at))"
                " FROM learn.silver__weather"
            )
            weather_dupes = cur.fetchone()[0]

            # --- plausibility: odd, not necessarily wrong ---------------
            plausibility = {}
            for name, (lo, hi) in WEATHER_RANGE.items():
                cur.execute(
                    "SELECT count(*) FILTER (WHERE value IS NULL),"
                    "       count(*) FILTER (WHERE value < %s OR value > %s)"
                    " FROM learn.silver__weather"
                    " WHERE station = %s AND parameter = %s",
                    (lo, hi, STATION, name),
                )
                plausibility[name] = cur.fetchone()

            lo, hi = PRICE_RANGE
            cur.execute(
                "SELECT count(*) FILTER (WHERE sek_per_kwh IS NULL),"
                "       count(*) FILTER (WHERE sek_per_kwh < %s OR sek_per_kwh > %s)"
                " FROM learn.silver__elpris WHERE price_area = %s",
                (lo, hi, AREA),
            )
            plausibility["prices"] = cur.fetchone()
    finally:
        conn.close()

    # --- compare every day with the calendar --------------------------
    problems = []
    summary = {}
    for name in ["prices", *WEATHER_RANGE]:
        complete = 0
        missing = 0
        for day in days:
            if name == "prices":
                expected = expected_price_intervals(day)
                found = price_counts.get(day, 0)
            else:
                expected = expected_weather_readings(day)
                found = weather_counts.get((name, day), 0)

            if found == expected:
                complete += 1
            else:
                problems.append((day, name, expected, found))
                missing += expected - found
        summary[name] = (complete, missing)

    # --- report --------------------------------------------------------
    print(f"Validating {start} .. {end}  ({len(days)} days)\n")

    print("Completeness")
    for name, (complete, missing) in summary.items():
        unit = "intervals" if name == "prices" else "readings"
        print(f"  {name:12} {complete}/{len(days)} days complete, {missing} {unit} missing")

    if problems:
        print("\nDays that don't match the calendar")
        for day, name, expected, found in sorted(problems):
            print(f"  {day}  {name:12} expected {expected:>3}  found {found:>3}"
                  f"  ({found - expected:+d})")

    print("\nStructure (must always be 0)")
    print(f"  duplicate price intervals   {price_dupes}")
    print(f"  duplicate weather readings  {weather_dupes}")

    print("\nPlausibility (worth a look, not necessarily wrong)")
    for name, (nulls, outside) in plausibility.items():
        lo, hi = PRICE_RANGE if name == "prices" else WEATHER_RANGE[name]
        print(f"  {name:12} {nulls} null, {outside} outside {lo}..{hi}")

    # --- decide: what in the recent days must stop the pipeline -------
    failures = []
    warnings = []
    for day, name, expected, found in sorted(problems):
        if day < recent_from:
            continue
        if name == "prices":
            failures.append(f"{day}  prices       {expected - found} intervals missing")
            continue
        gap = longest_gap(day, recent_hours.get(name, set()))
        line = f"{day}  {name:12} {expected - found} missing, longest gap {gap} h"
        (failures if gap > MAX_GAP_HOURS else warnings).append(line)

    print(f"\nLast {RECENT_DAYS} days"
          f" (weather gaps up to {MAX_GAP_HOURS} h are filled by features)")
    for line in failures:
        print(f"  FAIL  {line}")
    for line in warnings:
        print(f"  warn  {line}")
    if not failures and not warnings:
        print("  complete")

    print()
    if failures or price_dupes or weather_dupes:
        print(f"FAIL: unusable gaps in the last {RECENT_DAYS} days, or broken structure")
        sys.exit(1)
    print(f"OK: last {RECENT_DAYS} days usable, structure intact")


if __name__ == "__main__":
    main()