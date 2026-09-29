from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def compute_utc_schedule(
    local_time: str, tz_name: str, *, reference_date: date | None = None
) -> tuple[int, int]:
    parsed_time = time.fromisoformat(local_time)
    anchor_date = reference_date or datetime.now(UTC).date()
    local_dt = datetime.combine(anchor_date, parsed_time, tzinfo=ZoneInfo(tz_name))
    utc_dt = local_dt.astimezone(UTC)
    return utc_dt.hour, utc_dt.minute
