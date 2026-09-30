import logging
import threading
from collections.abc import Callable
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def run_daily_at(
    cycle: Callable[[], None],
    run_at: time,
    zone: ZoneInfo,
    stop_requested: threading.Event,
    *,
    clock: Callable[[], datetime] | None = None,
) -> None:
    now = clock or (lambda: datetime.now(zone))
    while not stop_requested.is_set():
        current = now()
        wait_seconds = (_next_run_at(current, run_at) - current).total_seconds()
        if stop_requested.wait(wait_seconds):
            return
        try:
            cycle()
        except Exception:
            logger.exception("fetch cycle failed; will retry at the next scheduled run")


def _next_run_at(current: datetime, run_at: time) -> datetime:
    candidate = current.replace(
        hour=run_at.hour, minute=run_at.minute, second=0, microsecond=0
    )
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate
