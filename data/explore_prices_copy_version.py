from datetime import date

import requests

AREA = "SE3"

def fetch_prices(day: date):
    url = f"https://www.elprisetjustnu.se/api/v1/prices/{day:%Y}/{day:%m-%d}_{AREA}.json"
    r = requests.get(url, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()

days = {
    date(2025, 9, 15):  "normal day, before the switch",
    date(2026, 9, 15):  "normal day, after the switch",
    date(2025, 10, 26): "autumn DST day, after the switch",
    date(2026, 3, 29):  "spring DST day, after the switch",
    date(2026, 9, 25):  "a day in the future",
}

for day, label in days.items():
    print(f"{day}  ({label})")
    data = fetch_prices(day)
    if data is None:
        print("   404 — not published\n")
        continue
    print(f"   intervals: {len(data)}")
    print(f"   first:     {data[0]['time_start']}")
    print(f"   last:      {data[-1]['time_start']}")
    print(f"   types:     SEK_per_kWh is {type(data[0]['SEK_per_kWh']).__name__}\n")

# Look inside the autumn DST day at the hour that happens twice
print("The repeated hour on 2025-10-26:")
for row in fetch_prices(date(2025, 10, 26)):
    if "T02:" in row["time_start"]:
        print("  ", row["time_start"])