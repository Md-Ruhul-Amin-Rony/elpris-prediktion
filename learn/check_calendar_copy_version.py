from datetime import date

from swedish_time_copy_version import expected_price_intervals as e

print(e(date(2025, 3, 30)), e(date(2024, 10, 27)), e(date(2026, 3, 29)), e(date(2025, 10, 26)))