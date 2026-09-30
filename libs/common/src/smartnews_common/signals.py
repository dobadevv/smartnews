import signal
from collections.abc import Callable

SHUTDOWN_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def call_on_shutdown_signals(callback: Callable[[], None]) -> None:
    for signum in SHUTDOWN_SIGNALS:
        signal.signal(signum, lambda _signum, _frame: callback())
