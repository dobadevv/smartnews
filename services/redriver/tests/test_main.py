import threading
from zoneinfo import ZoneInfo

import pytest
from smartnews_redriver import __main__ as main_module
from smartnews_redriver.config import RedriverConfig


class RecordingPass:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self._error = error

    def __call__(self) -> None:
        self.calls += 1
        if self._error is not None:
            raise self._error


@pytest.fixture
def run_hourly_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        main_module, "run_hourly", lambda **kwargs: calls.append(kwargs)
    )
    return calls


def test_start_runs_a_single_pass_and_skips_the_schedule_when_run_once_is_true(
    run_hourly_calls: list[dict[str, object]],
) -> None:
    redrive_pass = RecordingPass()

    main_module._start(
        redrive_pass=redrive_pass,
        config=RedriverConfig(run_once=True),
        zone=ZoneInfo("UTC"),
        stop_requested=threading.Event(),
    )

    assert redrive_pass.calls == 1
    assert run_hourly_calls == []


def test_start_lets_a_failing_single_pass_propagate_so_the_process_exits_non_zero(
    run_hourly_calls: list[dict[str, object]],
) -> None:
    with pytest.raises(ConnectionError):
        main_module._start(
            redrive_pass=RecordingPass(error=ConnectionError("rabbitmq down")),
            config=RedriverConfig(run_once=True),
            zone=ZoneInfo("UTC"),
            stop_requested=threading.Event(),
        )

    assert run_hourly_calls == []


def test_start_enters_the_hourly_schedule_when_run_once_is_false(
    run_hourly_calls: list[dict[str, object]],
) -> None:
    redrive_pass = RecordingPass()
    zone = ZoneInfo("UTC")
    stop_requested = threading.Event()

    main_module._start(
        redrive_pass=redrive_pass,
        config=RedriverConfig(run_once=False),
        zone=zone,
        stop_requested=stop_requested,
    )

    assert run_hourly_calls == [
        {"redrive_pass": redrive_pass, "zone": zone, "stop_requested": stop_requested}
    ]
    assert redrive_pass.calls == 0


def test_main_redrives_with_the_configured_queues_delay_and_message_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = RedriverConfig(
        run_once=True, delay_seconds=2, max_messages_per_run=7, queues=["a"]
    )
    pass_arguments: list[dict[str, object]] = []
    monkeypatch.setattr(main_module, "load_redriver_config", lambda path: config)
    monkeypatch.setattr(main_module, "require_env", lambda name: "amqp://test")
    monkeypatch.setattr(main_module, "call_on_shutdown_signals", lambda handler: None)
    monkeypatch.setattr(
        main_module,
        "run_redrive_pass",
        lambda **arguments: pass_arguments.append(arguments),
    )

    main_module.main()

    assert len(pass_arguments) == 1
    assert {
        name: value
        for name, value in pass_arguments[0].items()
        if name != "stop_requested"
    } == {
        "rabbitmq_url": "amqp://test",
        "queues": ["a"],
        "delay_seconds": 2,
        "max_messages_per_run": 7,
    }
