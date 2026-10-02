from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")

start = datetime.combine(date(2025, 10, 26), time.min, tzinfo=STOCKHOLM)
end   = datetime.combine(date(2025, 10, 27), time.min, tzinfo=STOCKHOLM)

print("start:                 ", start)
print("end:                   ", end)
print("end - start:           ", end - start)
print("same, compared in UTC: ", end.astimezone(UTC) - start.astimezone(UTC))