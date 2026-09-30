import logging
import threading
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
from smartnews_fetcher.loop import _next_run_at, run_daily_at


def test_next_run_at_is_today_when_run_at_has_not_passed_yet() -> None:
    current = datetime(2024, 1, 1, 6, 59, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    next_run = _next_run_at(current, time(7, 0))

    assert next_run == datetime(2024, 1, 1, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_next_run_at_is_tomorrow_when_run_at_already_passed_today() -> None:
    current = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    next_run = _next_run_at(current, time(7, 0))

    assert next_run == datetime(2024, 1, 2, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_next_run_at_is_tomorrow_when_current_time_exactly_matches_run_at() -> None:
    current = datetime(2024, 1, 1, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))

    next_run = _next_run_at(current, time(7, 0))

    assert next_run == datetime(2024, 1, 2, 7, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def test_run_daily_at_keeps_running_after_a_cycle_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop_requested = threading.Event()
    calls: list[int] = []
    just_before_run_at = datetime(2024, 1, 1, 11, 59, 59, 999_900, tzinfo=UTC)

    def cycle() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise ConnectionError("rabbitmq down")
        stop_requested.set()

    with caplog.at_level(logging.ERROR):
        run_daily_at(
            cycle,
            time(12, 0),
            ZoneInfo("UTC"),
            stop_requested,
            clock=lambda: just_before_run_at,
        )

    assert len(calls) == 2
    assert any("fetch cycle failed" in record.getMessage() for record in caplog.records)


def test_run_daily_at_does_not_run_when_stop_was_already_requested() -> None:
    stop_requested = threading.Event()
    stop_requested.set()
    calls: list[None] = []

    run_daily_at(
        lambda: calls.append(None), time(7, 0), ZoneInfo("UTC"), stop_requested
    )

    assert calls == []


def test_run_daily_at_returns_promptly_when_stopped_during_the_wait() -> None:
    stop_requested = threading.Event()
    far_from_run_at = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    calls: list[None] = []
    threading.Timer(0.05, stop_requested.set).start()

    finished = threading.Event()
    thread = threading.Thread(
        target=lambda: (
            run_daily_at(
                lambda: calls.append(None),
                time(12, 0),
                ZoneInfo("UTC"),
                stop_requested,
                clock=lambda: far_from_run_at,
            ),
            finished.set(),
        )
    )
    thread.start()

    assert finished.wait(timeout=5)
    assert calls == []
