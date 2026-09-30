import logging
import threading
from datetime import timedelta

import pytest
from smartnews_fetcher.loop import run_forever


def test_run_forever_keeps_running_after_a_cycle_fails(caplog: pytest.LogCaptureFixture) -> None:
    stop_requested = threading.Event()
    calls: list[int] = []

    def cycle() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise ConnectionError("rabbitmq down")
        stop_requested.set()

    with caplog.at_level(logging.ERROR):
        run_forever(cycle, timedelta(0), stop_requested)

    assert len(calls) == 2
    assert any("fetch cycle failed" in record.getMessage() for record in caplog.records)


def test_run_forever_does_not_run_when_stop_was_already_requested() -> None:
    stop_requested = threading.Event()
    stop_requested.set()
    calls: list[None] = []

    run_forever(lambda: calls.append(None), timedelta(0), stop_requested)

    assert calls == []


def test_run_forever_returns_promptly_when_stopped_during_the_wait() -> None:
    stop_requested = threading.Event()

    def cycle() -> None:
        threading.Timer(0.05, stop_requested.set).start()

    finished = threading.Event()
    thread = threading.Thread(
        target=lambda: (run_forever(cycle, timedelta(hours=1), stop_requested), finished.set())
    )
    thread.start()

    assert finished.wait(timeout=5)
