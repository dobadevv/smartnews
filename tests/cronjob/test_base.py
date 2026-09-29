from datetime import date

from smartnews.cronjob.base import compute_utc_schedule


def test_compute_utc_schedule_converts_vietnam_morning_time_to_utc() -> None:
    hour_utc, minute_utc = compute_utc_schedule("07:00", "Asia/Ho_Chi_Minh")

    assert (hour_utc, minute_utc) == (0, 0)


def test_compute_utc_schedule_wraps_to_previous_utc_day() -> None:
    hour_utc, minute_utc = compute_utc_schedule("02:00", "Asia/Ho_Chi_Minh")

    assert (hour_utc, minute_utc) == (19, 0)


def test_compute_utc_schedule_uses_summer_dst_offset_for_reference_date() -> None:
    hour_utc, minute_utc = compute_utc_schedule(
        "07:00", "America/New_York", reference_date=date(2026, 7, 15)
    )

    assert (hour_utc, minute_utc) == (11, 0)


def test_compute_utc_schedule_uses_winter_offset_for_reference_date() -> None:
    hour_utc, minute_utc = compute_utc_schedule(
        "07:00", "America/New_York", reference_date=date(2026, 1, 15)
    )

    assert (hour_utc, minute_utc) == (12, 0)
