import threading
from zoneinfo import ZoneInfo

from smartnews_fetcher import __main__ as main_module
from smartnews_fetcher.config import FetcherConfig


class RecordingCycle:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return 0


def test_start_runs_a_single_cycle_and_skips_the_loop_when_run_once_is_true(
    monkeypatch,
) -> None:
    run_daily_at_calls = []
    monkeypatch.setattr(
        main_module,
        "run_daily_at",
        lambda *args, **kwargs: run_daily_at_calls.append((args, kwargs)),
    )
    cycle = RecordingCycle()

    main_module._start(
        run_one_cycle=cycle,
        config=FetcherConfig(run_once=True, sources=[]),
        zone=ZoneInfo("UTC"),
        stop_requested=threading.Event(),
    )

    assert cycle.calls == 1
    assert run_daily_at_calls == []


def test_start_enters_the_daily_loop_when_run_once_is_false(monkeypatch) -> None:
    run_daily_at_calls = []
    monkeypatch.setattr(
        main_module,
        "run_daily_at",
        lambda *args, **kwargs: run_daily_at_calls.append((args, kwargs)),
    )
    cycle = RecordingCycle()
    config = FetcherConfig(run_once=False, sources=[])
    zone = ZoneInfo("UTC")
    stop_requested = threading.Event()

    main_module._start(
        run_one_cycle=cycle, config=config, zone=zone, stop_requested=stop_requested
    )

    assert len(run_daily_at_calls) == 1
    args, _ = run_daily_at_calls[0]
    cycle_fn, run_at, passed_zone, passed_stop = args
    assert (run_at, passed_zone, passed_stop) == (config.run_at, zone, stop_requested)
    assert cycle.calls == 0
    cycle_fn()
    assert cycle.calls == 1
