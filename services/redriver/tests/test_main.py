import logging
import threading
from zoneinfo import ZoneInfo

import pytest
from smartnews_redriver import __main__ as main_module
from smartnews_redriver.__main__ import Job
from smartnews_redriver.config import RedriverConfig, RetransformConfig

UTC_ZONE = ZoneInfo("UTC")
RETRANSFORM_DISABLED = RetransformConfig(enabled=False)


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


def start(
    jobs: list[Job],
    config: RedriverConfig,
    stop_requested: threading.Event | None = None,
) -> None:
    main_module._start(
        jobs=jobs,
        config=config,
        zone=UTC_ZONE,
        stop_requested=stop_requested or threading.Event(),
    )


def test_start_runs_each_pass_once_and_skips_the_schedule_when_run_once_is_true(
    run_hourly_calls: list[dict[str, object]],
) -> None:
    redrive_pass = RecordingPass()
    retransform_pass = RecordingPass()

    start(
        jobs=[
            Job(name="redrive", run_pass=redrive_pass),
            Job(name="retransform", run_pass=retransform_pass),
        ],
        config=RedriverConfig(run_once=True),
    )

    assert (redrive_pass.calls, retransform_pass.calls) == (1, 1)
    assert run_hourly_calls == []


def test_start_runs_the_passes_concurrently() -> None:
    retransform_ran = threading.Event()
    redrive_saw_retransform: list[bool] = []

    def redrive_pass() -> None:
        redrive_saw_retransform.append(retransform_ran.wait(timeout=5))

    start(
        jobs=[
            Job(name="redrive", run_pass=redrive_pass),
            Job(name="retransform", run_pass=retransform_ran.set),
        ],
        config=RedriverConfig(run_once=True),
    )

    assert redrive_saw_retransform == [True]


def test_start_still_runs_the_other_pass_and_then_raises_when_one_fails(
    run_hourly_calls: list[dict[str, object]], caplog: pytest.LogCaptureFixture
) -> None:
    retransform_pass = RecordingPass()

    with caplog.at_level(logging.ERROR), pytest.raises(ConnectionError):
        start(
            jobs=[
                Job(
                    name="redrive",
                    run_pass=RecordingPass(error=ConnectionError("rabbitmq down")),
                ),
                Job(name="retransform", run_pass=retransform_pass),
            ],
            config=RedriverConfig(run_once=True),
        )

    assert retransform_pass.calls == 1
    assert "redrive pass failed" in caplog.text
    assert run_hourly_calls == []


def test_start_raises_the_first_failure_in_start_order_and_logs_both(
    caplog: pytest.LogCaptureFixture,
) -> None:
    retransform_failed = threading.Event()

    def redrive_pass() -> None:
        retransform_failed.wait(timeout=5)
        raise ConnectionError("rabbitmq down")

    def retransform_pass() -> None:
        retransform_failed.set()
        raise RuntimeError("database down")

    with caplog.at_level(logging.ERROR), pytest.raises(ConnectionError):
        start(
            jobs=[
                Job(name="redrive", run_pass=redrive_pass),
                Job(name="retransform", run_pass=retransform_pass),
            ],
            config=RedriverConfig(run_once=True),
        )

    assert "redrive pass failed" in caplog.text
    assert "retransform pass failed" in caplog.text


def test_start_runs_every_job_on_the_hourly_schedule_when_run_once_is_false(
    run_hourly_calls: list[dict[str, object]],
) -> None:
    redrive_pass = RecordingPass()
    retransform_pass = RecordingPass()
    stop_requested = threading.Event()

    start(
        jobs=[
            Job(name="redrive", run_pass=redrive_pass),
            Job(name="retransform", run_pass=retransform_pass),
        ],
        config=RedriverConfig(run_once=False),
        stop_requested=stop_requested,
    )

    assert sorted(run_hourly_calls, key=lambda call: str(call["job_name"])) == [
        {
            "run_pass": redrive_pass,
            "job_name": "redrive",
            "zone": UTC_ZONE,
            "stop_requested": stop_requested,
        },
        {
            "run_pass": retransform_pass,
            "job_name": "retransform",
            "zone": UTC_ZONE,
            "stop_requested": stop_requested,
        },
    ]
    assert (redrive_pass.calls, retransform_pass.calls) == (0, 0)


class FakeEngine:
    def __init__(self) -> None:
        self.dispose_calls = 0

    def dispose(self) -> None:
        self.dispose_calls += 1


class MainDoubles:
    """Replaces main's config, environment, engine and passes with recorders."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config: RedriverConfig,
        redrive_error: Exception | None = None,
    ) -> None:
        self.requested_env: list[str] = []
        self.engine_urls: list[str] = []
        self.engine = FakeEngine()
        self.redrive_arguments: list[dict[str, object]] = []
        self.retransform_arguments: list[dict[str, object]] = []
        environment = {
            "RABBITMQ_URL": "amqp://test",
            "DATABASE_URL": "postgresql://test",
        }

        def require_env(name: str) -> str:
            self.requested_env.append(name)
            return environment[name]

        def create_database_engine(database_url: str) -> FakeEngine:
            self.engine_urls.append(database_url)
            return self.engine

        def run_redrive_pass(**arguments: object) -> None:
            self.redrive_arguments.append(arguments)
            if redrive_error is not None:
                raise redrive_error

        def run_retransform_pass(**arguments: object) -> None:
            self.retransform_arguments.append(arguments)

        monkeypatch.setattr(main_module, "load_redriver_config", lambda path: config)
        monkeypatch.setattr(main_module, "require_env", require_env)
        monkeypatch.setattr(
            main_module, "call_on_shutdown_signals", lambda handler: None
        )
        monkeypatch.setattr(
            main_module, "create_database_engine", create_database_engine
        )
        monkeypatch.setattr(main_module, "run_redrive_pass", run_redrive_pass)
        monkeypatch.setattr(main_module, "run_retransform_pass", run_retransform_pass)


def without_stop_event(arguments: dict[str, object]) -> dict[str, object]:
    return {name: value for name, value in arguments.items() if name != "stop_requested"}


def test_main_redrives_with_the_configured_queues_delay_and_message_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles = MainDoubles(
        monkeypatch=monkeypatch,
        config=RedriverConfig(
            run_once=True,
            delay_seconds=2,
            max_messages_per_run=7,
            queues=["a"],
            retransform=RETRANSFORM_DISABLED,
        ),
    )

    main_module.main()

    assert [without_stop_event(arguments) for arguments in doubles.redrive_arguments] == [
        {
            "rabbitmq_url": "amqp://test",
            "queues": ["a"],
            "delay_seconds": 2,
            "max_messages_per_run": 7,
        }
    ]


def test_main_with_retransform_disabled_never_reads_the_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles = MainDoubles(
        monkeypatch=monkeypatch,
        config=RedriverConfig(run_once=True, retransform=RETRANSFORM_DISABLED),
    )

    main_module.main()

    assert doubles.requested_env == ["RABBITMQ_URL"]
    assert doubles.engine_urls == []
    assert doubles.retransform_arguments == []
    assert len(doubles.redrive_arguments) == 1


def test_main_retransforms_with_the_configured_minimum_age_delay_and_message_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles = MainDoubles(
        monkeypatch=monkeypatch,
        config=RedriverConfig(
            run_once=True,
            delay_seconds=2,
            max_messages_per_run=7,
            retransform=RetransformConfig(min_age_minutes=15),
        ),
    )

    main_module.main()

    assert doubles.engine_urls == ["postgresql://test"]
    assert [
        without_stop_event(arguments) for arguments in doubles.retransform_arguments
    ] == [
        {
            "engine": doubles.engine,
            "rabbitmq_url": "amqp://test",
            "min_age_minutes": 15,
            "delay_seconds": 2,
            "max_messages_per_run": 7,
        }
    ]
    assert (
        doubles.retransform_arguments[0]["stop_requested"]
        is doubles.redrive_arguments[0]["stop_requested"]
    )
    assert doubles.engine.dispose_calls == 1


def test_main_starts_both_jobs_on_the_hourly_schedule(
    monkeypatch: pytest.MonkeyPatch, run_hourly_calls: list[dict[str, object]]
) -> None:
    doubles = MainDoubles(monkeypatch=monkeypatch, config=RedriverConfig(run_once=False))

    main_module.main()

    assert sorted(str(call["job_name"]) for call in run_hourly_calls) == [
        "redrive",
        "retransform",
    ]
    assert doubles.engine.dispose_calls == 1


def test_main_disposes_the_engine_when_a_run_once_pass_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doubles = MainDoubles(
        monkeypatch=monkeypatch,
        config=RedriverConfig(run_once=True),
        redrive_error=ConnectionError("rabbitmq down"),
    )

    with pytest.raises(ConnectionError):
        main_module.main()

    assert doubles.engine.dispose_calls == 1
    assert len(doubles.retransform_arguments) == 1
