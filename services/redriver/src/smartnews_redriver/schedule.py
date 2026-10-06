import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def run_hourly(
    run_pass: Callable[[], None],
    zone: ZoneInfo,
    stop_requested: threading.Event,
    *,
    job_name: str,
    clock: Callable[[], datetime] | None = None,
) -> None:
    now = clock or (lambda: datetime.now(zone))
    while not stop_requested.is_set():
        current = now()
        wait_seconds = _seconds_between(start=current, end=_next_top_of_hour(current))
        if stop_requested.wait(wait_seconds):
            return
        try:
            run_pass()
        except Exception:
            logger.exception(
                "%s pass failed; will retry at the next top of the hour", job_name
            )


def _next_top_of_hour(current: datetime) -> datetime:
    top = current.replace(minute=0, second=0, microsecond=0)
    # Adding the hour to the UTC instant keeps it one real hour across DST shifts.
    return (top.astimezone(UTC) + timedelta(hours=1)).astimezone(current.tzinfo)


def _seconds_between(start: datetime, end: datetime) -> float:
    # Aware datetimes sharing a tzinfo subtract as wall-clock times, which is
    # off by the DST shift around a transition; UTC instants give elapsed time.
    return (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds()
