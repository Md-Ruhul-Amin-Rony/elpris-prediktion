import requests

STATION = 97400
PARAMETERS = {"temperature": 1, "wind": 4}

for name, param_id in PARAMETERS.items():
    url = (
        "https://opendata-download-metobs.smhi.se/api/version/1.0"
        f"/parameter/{param_id}/station/{STATION}/period/corrected-archive/data.csv"
    )
    r = requests.get(url, timeout=120)
    print(f"===== {name}  HTTP {r.status_code}  {len(r.content):,} bytes")
    r.raise_for_status()

    lines = r.content.decode("utf-8", errors="replace").splitlines()
    print(f"total lines: {len(lines):,}\n")

    print("--- first 12 lines ---")
    for line in lines[:12]:
        print(repr(line))

    print("\n--- first rows from 2024-08-01 ---")
    for line in [l for l in lines if l.startswith("2024-08-01")][:3]:
        print(repr(line))

    print("\n--- last 3 lines ---")
    for line in lines[-3:]:
        print(repr(line))
    print()