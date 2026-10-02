from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import requests

STATION = 97400
STOCKHOLM = ZoneInfo("Europe/Stockholm")
url = (
    "https://opendata-download-metobs.smhi.se/api/version/1.0"
    f"/parameter/1/station/{STATION}/period/latest-months/data.json"
)

r = requests.get(url, timeout=30)
print("HTTP", r.status_code)
r.raise_for_status()
payload = r.json()

print("top-level keys:", list(payload.keys()))
print("station name:  ", payload["station"]["name"])
print("readings:      ", len(payload["value"]))
print()

for v in payload["value"][-3:]:
    ms = v["date"]
    naive = datetime.fromtimestamp(ms / 1000)
    aware = datetime.fromtimestamp(ms / 1000, tz=UTC)
    print(f"raw date     {ms}")
    print(f"  naive      {naive}    tzinfo={naive.tzinfo}")
    print(f"  aware UTC  {aware}")
    print(f"  Swedish    {aware.astimezone(STOCKHOLM)}")
    print(f"  value      {v['value']!r}   quality {v['quality']}")
    print()