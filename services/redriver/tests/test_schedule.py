import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from smartnews_redriver.schedule import _next_top_of_hour, run_hourly

HO_CHI_MINH = ZoneInfo("Asia/Ho_Chi_Minh")
KOLKATA = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")


class RecordingStopEvent(threading.Event):
    """Records requested waits instead of sleeping; sets itself on wait number `stop_on_wait`."""

    def __init__(self, stop_on_wait: int | None = None) -> None:
        super().__init__()
        self.waits: list[float | None] = []
        self._stop_on_wait = stop_on_wait

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        if len(self.waits) == self._stop_on_wait:
            self.set()
        return self.is_set()


def clock_reading(*instants: datetime) -> Callable[[], datetime]:
    return iter(instants).__next__


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        pytest.param(
            datetime(2026, 10, 6, 2, 17, 45, tzinfo=HO_CHI_MINH),
            datetime(2026, 10, 6, 3, 0, tzinfo=HO_CHI_MINH),
            id="mid-hour",
        ),
        pytest.param(
            datetime(2026, 10, 6, 3, 0, tzinfo=HO_CHI_MINH),
            datetime(2026, 10, 6, 4, 0, tzinfo=HO_CHI_MINH),
            id="exactly-on-the-hour-is-the-next-hour",
        ),
        pytest.param(
            datetime(2026, 10, 6, 2, 59, 59, 999_999, tzinfo=HO_CHI_MINH),
            datetime(2026, 10, 6, 3, 0, tzinfo=HO_CHI_MINH),
            id="one-microsecond-before-the-hour",
        ),
        pytest.param(
            datetime(2026, 10, 6, 23, 30, tzinfo=HO_CHI_MINH),
            datetime(2026, 10, 7, 0, 0, tzinfo=HO_CHI_MINH),
            id="day-rollover",
        ),
        pytest.param(
            datetime(2026, 12, 31, 23, 59, tzinfo=HO_CHI_MINH),
            datetime(2027, 1, 1, 0, 0, tzinfo=HO_CHI_MINH),
            id="year-rollover",
        ),
        pytest.param(
            datetime(2026, 10, 6, 10, 15, tzinfo=KOLKATA),
            datetime(2026, 10, 6, 11, 0, tzinfo=KOLKATA),
            id="half-hour-offset-zone-uses-local-hours",
        ),
    ],
)
def test_next_top_of_hour(current: datetime, expected: datetime) -> None:
    assert _next_top_of_hour(current) == expected


def test_next_top_of_hour_is_one_real_hour_after_the_top_across_a_dst_fall_back() -> (
    None
):
    first_one_thirty = datetime(2026, 11, 1, 1, 30, tzinfo=NEW_YORK)  # EDT, 05:30 UTC

    next_run = _next_top_of_hour(first_one_thirty)

    assert next_run.astimezone(UTC) == datetime(2026, 11, 1, 6, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("zone", "current", "expected_wait_seconds"),
    [
        pytest.param(
            HO_CHI_MINH,
            datetime(2026, 10, 6, 2, 17, 45, tzinfo=HO_CHI_MINH),
            2535.0,
            id="mid-hour",
        ),
        pytest.param(
            NEW_YORK,
            datetime(2026, 11, 1, 1, 30, tzinfo=NEW_YORK),
            1800.0,
            id="across-a-dst-fall-back",
        ),
    ],
)
def test_run_hourly_waits_the_real_seconds_until_the_next_top_of_the_hour(
    zone: ZoneInfo, current: datetime, expected_wait_seconds: float
) -> None:
    stop_requested = RecordingStopEvent(stop_on_wait=1)
    passes: list[None] = []

    run_hourly(
        redrive_pass=lambda: passes.append(None),
        zone=zone,
        stop_requested=stop_requested,
        clock=clock_reading(current),
    )

    assert stop_requested.waits == [expected_wait_seconds]
    assert passes == []


def test_run_hourly_logs_a_failing_pass_and_runs_again_next_hour(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop_requested = RecordingStopEvent(stop_on_wait=3)
    passes: list[None] = []

    def redrive_pass() -> None:
        passes.append(None)
        if len(passes) == 1:
            raise ConnectionError("rabbitmq down")

    with caplog.at_level(logging.ERROR):
        run_hourly(
            redrive_pass=redrive_pass,
            zone=HO_CHI_MINH,
            stop_requested=stop_requested,
            clock=clock_reading(
                *[datetime(2026, 10, 6, 2, 30, tzinfo=HO_CHI_MINH)] * 3
            ),
        )

    assert len(passes) == 2
    assert "redrive pass failed; will retry at the next top of the hour" in caplog.text


def test_run_hourly_recomputes_the_next_run_after_an_overrunning_pass() -> None:
    stop_requested = RecordingStopEvent(stop_on_wait=2)
    passes: list[None] = []

    run_hourly(
        redrive_pass=lambda: passes.append(None),
        zone=HO_CHI_MINH,
        stop_requested=stop_requested,
        clock=clock_reading(
            datetime(2026, 10, 6, 2, 30, tzinfo=HO_CHI_MINH),
            datetime(2026, 10, 6, 4, 2, tzinfo=HO_CHI_MINH),
        ),
    )

    assert stop_requested.waits == [1800.0, 3480.0]
    assert len(passes) == 1


def test_run_hourly_does_nothing_when_stop_was_already_requested() -> None:
    stop_requested = RecordingStopEvent()
    stop_requested.set()
    passes: list[None] = []

    run_hourly(
        redrive_pass=lambda: passes.append(None),
        zone=HO_CHI_MINH,
        stop_requested=stop_requested,
    )

    assert passes == []
    assert stop_requested.waits == []


def test_run_hourly_returns_promptly_when_stopped_during_the_wait() -> None:
    stop_requested = threading.Event()
    passes: list[None] = []
    finished = threading.Event()

    def run() -> None:
        run_hourly(
            redrive_pass=lambda: passes.append(None),
            zone=HO_CHI_MINH,
            stop_requested=stop_requested,
            clock=lambda: datetime(2026, 10, 6, 2, 0, tzinfo=HO_CHI_MINH),
        )
        finished.set()

    thread = threading.Thread(target=run)
    thread.start()
    stop_requested.set()

    assert finished.wait(timeout=5)
    assert passes == []
