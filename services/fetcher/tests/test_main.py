import threading
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from smartnews_fetcher import __main__ as main_module
from smartnews_fetcher.config import FetcherConfig
from smartnews_fetcher.cycle import CycleDeps


def make_deps(*, run_once: bool) -> CycleDeps:
    config = FetcherConfig(run_once=run_once, sources=[])
    return CycleDeps(
        config=config,
        fetcher=MagicMock(),
        engine=MagicMock(),
        rabbitmq_url="amqp://unused",
    )


def test_start_runs_a_single_cycle_and_skips_the_loop_when_run_once_is_true(
    monkeypatch,
) -> None:
    deps = make_deps(run_once=True)
    run_daily_at_calls = []
    monkeypatch.setattr(
        main_module,
        "run_daily_at",
        lambda *args, **kwargs: run_daily_at_calls.append((args, kwargs)),
    )
    cycle_calls = []
    monkeypatch.setattr(
        main_module, "run_cycle", lambda d: cycle_calls.append(d) or 0
    )

    main_module._start(deps, ZoneInfo("UTC"), threading.Event())

    assert cycle_calls == [deps]
    assert run_daily_at_calls == []


def test_start_enters_the_daily_loop_when_run_once_is_false(monkeypatch) -> None:
    deps = make_deps(run_once=False)
    run_daily_at_calls = []
    monkeypatch.setattr(
        main_module,
        "run_daily_at",
        lambda *args, **kwargs: run_daily_at_calls.append((args, kwargs)),
    )
    cycle_calls = []
    monkeypatch.setattr(
        main_module, "run_cycle", lambda d: cycle_calls.append(d) or 0
    )
    zone = ZoneInfo("UTC")
    stop_requested = threading.Event()

    main_module._start(deps, zone, stop_requested)

    assert len(run_daily_at_calls) == 1
    args, _ = run_daily_at_calls[0]
    cycle_fn, run_at, passed_zone, passed_stop = args
    assert (run_at, passed_zone, passed_stop) == (
        deps.config.run_at,
        zone,
        stop_requested,
    )
    cycle_fn()
    assert cycle_calls == [deps]
