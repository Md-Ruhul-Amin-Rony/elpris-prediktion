import requests
import argparse
import pandas as pd
def parse_args():
    parser = argparse.ArgumentParser(description="Fetch historical electricity prices")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument("--areas", nargs="+", default=["SE3"], help="Price areas, e.g. SE1 SE3")
    return parser.parse_args()

def fetch_prices_for_day(date_str: str, area: str) -> list[dict] | None:
    year, month, day = date_str.split("-")
    url = f"https://www.elprisetjustnu.se/api/v1/prices/{year}/{month}-{day}_{area}.json"
    response = requests.get(url)

    if response.status_code == 404:
        print(f"No data for {date_str} {area} (not published yet, or out of range)")
        return None

    response.raise_for_status()  # crash loudly on anything else unexpected, e.g. 500
    return response.json()



import time
from datetime import date, timedelta

def fetch_prices_for_range(start: date, end: date, areas: list[str]) -> list[dict]:
    all_rows = []
    current = start

    while current <= end:
        date_str = current.isoformat()  # e.g. "2025-01-15"

        for area in areas:
            rows = fetch_prices_for_day(date_str, area)
            if rows:
                for row in rows:
                    row["area"] = area  # tag each row with its area before merging
                all_rows.extend(rows)

            time.sleep(0.5)  # be polite to the free API between every call

        current += timedelta(days=1)

    return all_rows
def save_prices(rows: list[dict], path: str = "data/historik_elpris.csv.gz"):
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, compression="gzip")
    print(f"Saved {len(df)} rows to {path}")
    return df

if __name__ == "__main__":
    args = parse_args()
    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)

    rows = fetch_prices_for_range(start, end, args.areas)
    save_prices(rows)
    print(f"Fetched {len(rows)} rows for areas {args.areas}, {start} to {end}")