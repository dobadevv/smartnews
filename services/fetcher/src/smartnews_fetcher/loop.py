import logging
import threading
from collections.abc import Callable
from datetime import timedelta

logger = logging.getLogger(__name__)


def run_forever(
    cycle: Callable[[], None], interval: timedelta, stop_requested: threading.Event
) -> None:
    while not stop_requested.is_set():
        try:
            cycle()
        except Exception:
            logger.exception("fetch cycle failed; next attempt in %s", interval)
        stop_requested.wait(interval.total_seconds())
