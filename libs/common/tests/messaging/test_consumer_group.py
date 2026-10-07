import threading

import pytest
from smartnews_common.messaging.consumer_group import ConsumerGroup

JOIN_TIMEOUT_SECONDS = 5


class FakeConsumer:
    def __init__(self, error: Exception | None = None) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.consumed_one = threading.Event()
        self._error = error

    def run(self) -> None:
        self.started.set()
        if self._error is not None:
            raise self._error
        self.stopped.wait()

    def stop(self) -> None:
        self.stopped.set()

    def consume_one(self) -> None:
        if self._error is not None:
            raise self._error
        self.consumed_one.set()


def run_in_background(group: ConsumerGroup) -> tuple[threading.Thread, list[BaseException]]:
    errors: list[BaseException] = []

    def target() -> None:
        try:
            group.run()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=target)
    thread.start()
    return thread, errors


def test_run_runs_every_consumer_until_stopped() -> None:
    first, second = FakeConsumer(), FakeConsumer()
    group = ConsumerGroup([first, second])
    thread, errors = run_in_background(group)

    assert first.started.wait(JOIN_TIMEOUT_SECONDS)
    assert second.started.wait(JOIN_TIMEOUT_SECONDS)
    group.stop()
    thread.join(JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert errors == []
    assert first.stopped.is_set() and second.stopped.is_set()


def test_run_stops_the_other_consumers_and_reraises_when_one_fails() -> None:
    healthy, failing = FakeConsumer(), FakeConsumer(error=RuntimeError("boom"))
    thread, errors = run_in_background(ConsumerGroup([healthy, failing]))

    thread.join(JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive()
    assert healthy.stopped.is_set()
    assert [str(error) for error in errors] == ["boom"]


def test_consume_one_lets_every_consumer_take_one_message() -> None:
    first, second = FakeConsumer(), FakeConsumer()

    ConsumerGroup([first, second]).consume_one()

    assert first.consumed_one.is_set() and second.consumed_one.is_set()


def test_consume_one_reraises_a_failure_after_the_other_consumers_ran() -> None:
    failing, healthy = FakeConsumer(error=RuntimeError("boom")), FakeConsumer()

    with pytest.raises(RuntimeError, match="boom"):
        ConsumerGroup([failing, healthy]).consume_one()

    assert healthy.consumed_one.is_set()
