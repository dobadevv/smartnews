import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import (
    AMQPConnectionError,
    ChannelClosedByBroker,
    ConnectionWrongStateError,
    NackError,
    UnroutableError,
)
from pika.frame import Method
from pika.spec import Basic, Queue
from smartnews_redriver import redrive as redrive_module
from smartnews_redriver.redrive import RedriveResult, redrive_queue, run_redrive_pass

MAIN_QUEUE = "articles.crawl"
DEAD_LETTER_QUEUE = "articles.crawl.dlq"


@dataclass(frozen=True)
class DeadLetter:
    body: bytes
    headers: dict[str, int] | None = None


@dataclass(frozen=True)
class PublishedMessage:
    exchange: str
    routing_key: str
    body: bytes
    properties: pika.BasicProperties
    mandatory: bool


class FakeChannel:
    """Stands in for a confirmed BlockingChannel and records every broker call."""

    def __init__(
        self,
        dead_letters: dict[str, list[DeadLetter]] | None = None,
        declared_counts: dict[str, int] | None = None,
        declare_errors: dict[str, Exception] | None = None,
        publish_errors: dict[str, Exception] | None = None,
    ) -> None:
        self._dead_letters = {
            queue: list(messages) for queue, messages in (dead_letters or {}).items()
        }
        self._declared_counts = declared_counts or {}
        self._declare_errors = declare_errors or {}
        self._publish_errors = publish_errors or {}
        self._next_delivery_tag = 1
        self.is_open = True
        self.calls: list[tuple[str, object]] = []
        self.published: list[PublishedMessage] = []

    def confirm_delivery(self) -> None:
        self.calls.append(("confirm_delivery", None))

    def queue_declare(
        self, queue: str, passive: bool = False
    ) -> Method[Queue.DeclareOk]:
        self.calls.append(("queue_declare", queue))
        assert passive, "the redriver must never create queues"
        error = self._declare_errors.get(queue)
        if error is not None:
            self.is_open = not isinstance(error, ChannelClosedByBroker)
            raise error
        count = self._declared_counts.get(queue, len(self._dead_letters.get(queue, [])))
        return Method(
            1, Queue.DeclareOk(queue=queue, message_count=count, consumer_count=0)
        )

    def basic_get(
        self, queue: str, auto_ack: bool = False
    ) -> tuple[Basic.GetOk | None, pika.BasicProperties | None, bytes | None]:
        self.calls.append(("basic_get", queue))
        assert not auto_ack, (
            "a message must stay unacked until its republish is confirmed"
        )
        waiting = self._dead_letters.get(queue, [])
        if not waiting:
            return None, None, None
        dead_letter = waiting.pop(0)
        delivery_tag = self._next_delivery_tag
        self._next_delivery_tag += 1
        method = Basic.GetOk(
            delivery_tag=delivery_tag, exchange="smartnews", routing_key=queue
        )
        return (
            method,
            pika.BasicProperties(headers=dead_letter.headers),
            dead_letter.body,
        )

    def basic_publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: pika.BasicProperties,
        mandatory: bool,
    ) -> None:
        self.calls.append(("basic_publish", routing_key))
        error = self._publish_errors.get(routing_key)
        if error is not None:
            self.is_open = not isinstance(error, ChannelClosedByBroker)
            raise error
        self.published.append(
            PublishedMessage(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                properties=properties,
                mandatory=mandatory,
            )
        )

    def basic_ack(self, delivery_tag: int) -> None:
        self.calls.append(("basic_ack", delivery_tag))

    def basic_nack(self, delivery_tag: int, requeue: bool) -> None:
        self.calls.append(("basic_nack", (delivery_tag, requeue)))

    def calls_named(self, name: str) -> list[object]:
        return [argument for called, argument in self.calls if called == name]


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


def as_channel(fake: FakeChannel) -> BlockingChannel:
    return cast(BlockingChannel, fake)


def dead_letters(count: int) -> list[DeadLetter]:
    return [
        DeadLetter(body=f'{{"article_id": {number}}}'.encode())
        for number in range(count)
    ]


def redrive(
    channel: FakeChannel,
    delay_seconds: float = 0,
    stop_requested: threading.Event | None = None,
    max_messages_per_run: int = 100,
) -> RedriveResult:
    return redrive_queue(
        channel=as_channel(channel),
        queue=MAIN_QUEUE,
        delay_seconds=delay_seconds,
        stop_requested=stop_requested or RecordingStopEvent(),
        max_messages_per_run=max_messages_per_run,
    )


def test_redrive_queue_redrives_at_most_the_snapshot_count() -> None:
    channel = FakeChannel(
        dead_letters={DEAD_LETTER_QUEUE: dead_letters(3)},
        declared_counts={DEAD_LETTER_QUEUE: 2},
    )

    result = redrive(channel)

    assert result == RedriveResult(snapshot_count=2, redriven=2)
    assert len(channel.calls_named("basic_get")) == 2


def test_redrive_queue_redrives_at_most_the_per_run_limit() -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(5)})
    stop_requested = RecordingStopEvent()

    result = redrive(
        channel=channel,
        delay_seconds=5,
        stop_requested=stop_requested,
        max_messages_per_run=3,
    )

    assert result == RedriveResult(snapshot_count=5, redriven=3)
    assert len(channel.calls_named("basic_get")) == 3
    assert channel.calls_named("basic_ack") == [1, 2, 3]
    assert stop_requested.waits == [5, 5]


def test_redrive_queue_stops_when_the_dead_letter_queue_runs_dry() -> None:
    channel = FakeChannel(
        dead_letters={DEAD_LETTER_QUEUE: dead_letters(1)},
        declared_counts={DEAD_LETTER_QUEUE: 3},
    )

    result = redrive(channel)

    assert result == RedriveResult(snapshot_count=3, redriven=1)
    assert len(channel.calls_named("basic_get")) == 2


def test_redrive_queue_on_an_empty_dead_letter_queue_fetches_nothing() -> None:
    channel = FakeChannel()

    result = redrive(channel)

    assert result == RedriveResult(snapshot_count=0, redriven=0)
    assert channel.calls_named("basic_get") == []


@pytest.mark.parametrize(
    ("message_count", "delay_seconds", "expected_waits"),
    [
        pytest.param(1, 5.0, [], id="single-message-never-waits"),
        pytest.param(3, 5.0, [5.0, 5.0], id="waits-between-messages-only"),
        pytest.param(3, 0.0, [], id="zero-delay-never-waits"),
    ],
)
def test_redrive_queue_waits_the_delay_between_messages(
    message_count: int, delay_seconds: float, expected_waits: list[float]
) -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(message_count)})
    stop_requested = RecordingStopEvent()

    result = redrive(
        channel=channel, delay_seconds=delay_seconds, stop_requested=stop_requested
    )

    assert result.redriven == message_count
    assert stop_requested.waits == expected_waits


@pytest.mark.parametrize(
    "incoming_headers",
    [
        pytest.param({"x-attempt": 4}, id="after-the-final-retry"),
        pytest.param(None, id="no-headers"),
    ],
)
def test_redrive_queue_republishes_the_body_to_the_main_queue_as_a_first_attempt(
    incoming_headers: dict[str, int] | None,
) -> None:
    body = b'{"article_id": 7}'
    channel = FakeChannel(
        dead_letters={
            DEAD_LETTER_QUEUE: [DeadLetter(body=body, headers=incoming_headers)]
        }
    )

    redrive(channel)

    assert channel.published == [
        PublishedMessage(
            exchange="",
            routing_key=MAIN_QUEUE,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                headers={"x-attempt": 1},
            ),
            mandatory=True,
        )
    ]


def test_redrive_queue_acks_each_message_only_after_its_publish() -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(2)})

    redrive(channel)

    assert [call for call in channel.calls if call[0] != "queue_declare"] == [
        ("basic_get", DEAD_LETTER_QUEUE),
        ("basic_publish", MAIN_QUEUE),
        ("basic_ack", 1),
        ("basic_get", DEAD_LETTER_QUEUE),
        ("basic_publish", MAIN_QUEUE),
        ("basic_ack", 2),
    ]


@pytest.mark.parametrize(
    ("error", "expected_nacks"),
    [
        pytest.param(UnroutableError([]), [(1, True)], id="unroutable"),
        pytest.param(NackError([]), [(1, True)], id="nacked-by-broker"),
        pytest.param(
            ChannelClosedByBroker(406, "PRECONDITION_FAILED"),
            [],
            id="channel-closed-requeues-by-itself",
        ),
    ],
)
def test_redrive_queue_requeues_and_abandons_the_queue_when_a_publish_fails(
    error: Exception,
    expected_nacks: list[tuple[int, bool]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    channel = FakeChannel(
        dead_letters={DEAD_LETTER_QUEUE: dead_letters(2)},
        publish_errors={MAIN_QUEUE: error},
    )

    with caplog.at_level(logging.ERROR):
        result = redrive(channel)

    assert result == RedriveResult(snapshot_count=2, redriven=0)
    assert channel.calls_named("basic_nack") == expected_nacks
    assert channel.calls_named("basic_ack") == []
    assert len(channel.calls_named("basic_get")) == 1
    assert f"failed to redrive a message from {DEAD_LETTER_QUEUE}" in caplog.text


def test_redrive_queue_stops_when_stop_is_requested_during_a_delay() -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(3)})
    stop_requested = RecordingStopEvent(stop_on_wait=1)

    result = redrive(channel=channel, delay_seconds=5, stop_requested=stop_requested)

    assert result == RedriveResult(snapshot_count=3, redriven=1)
    assert channel.calls_named("basic_ack") == [1]
    assert len(channel.calls_named("basic_get")) == 1


def test_redrive_queue_without_a_delay_still_stops_between_messages() -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(3)})
    stop_requested = RecordingStopEvent()
    stop_requested.set()

    result = redrive(channel=channel, delay_seconds=0, stop_requested=stop_requested)

    assert result == RedriveResult(snapshot_count=3, redriven=1)
    assert stop_requested.waits == []


class FakeConnection:
    def __init__(self, channels: list[FakeChannel]) -> None:
        self._unopened = list(channels)
        self.opened: list[FakeChannel] = []
        self.is_open = True
        self.close_calls = 0

    def channel(self) -> FakeChannel:
        channel = self._unopened.pop(0)
        self.opened.append(channel)
        return channel

    def close(self) -> None:
        if not self.is_open:
            raise ConnectionWrongStateError("connection already closed")
        self.close_calls += 1
        self.is_open = False


ConnectTo = Callable[[FakeConnection], None]


@pytest.fixture
def connect_to(monkeypatch: pytest.MonkeyPatch) -> ConnectTo:
    def install(connection: FakeConnection) -> None:
        monkeypatch.setattr(
            redrive_module, "_open_connection", lambda rabbitmq_url: connection
        )

    return install


def run_pass(
    queues: list[str],
    delay_seconds: float = 0,
    stop_requested: threading.Event | None = None,
    max_messages_per_run: int = 100,
) -> None:
    run_redrive_pass(
        rabbitmq_url="amqp://unused",
        queues=queues,
        delay_seconds=delay_seconds,
        stop_requested=stop_requested or RecordingStopEvent(),
        max_messages_per_run=max_messages_per_run,
    )


def test_run_redrive_pass_redrives_every_queue_in_order_and_closes_the_connection(
    connect_to: ConnectTo, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel(
        dead_letters={"a.dlq": dead_letters(1), "b.dlq": dead_letters(2)}
    )
    connection = FakeConnection([channel])
    connect_to(connection)

    with caplog.at_level(logging.INFO):
        run_pass(["a", "b"])

    assert [message.routing_key for message in channel.published] == ["a", "b", "b"]
    assert "redrove 1 of 1 message(s) from a.dlq to a" in caplog.text
    assert "redrove 2 of 2 message(s) from b.dlq to b" in caplog.text
    assert connection.opened == [channel]
    assert channel.calls[0] == ("confirm_delivery", None)
    assert connection.close_calls == 1


def test_run_redrive_pass_applies_the_per_run_limit_to_each_queue(
    connect_to: ConnectTo, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel(
        dead_letters={"a.dlq": dead_letters(3), "b.dlq": dead_letters(3)}
    )
    connect_to(FakeConnection([channel]))

    with caplog.at_level(logging.INFO):
        run_pass(queues=["a", "b"], max_messages_per_run=2)

    assert [message.routing_key for message in channel.published] == [
        "a",
        "a",
        "b",
        "b",
    ]
    assert "redrove 2 of 3 message(s) from a.dlq to a (limit 2)" in caplog.text
    assert "redrove 2 of 3 message(s) from b.dlq to b (limit 2)" in caplog.text


def test_run_redrive_pass_moves_on_to_the_next_queue_after_a_publish_failure(
    connect_to: ConnectTo, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel(
        dead_letters={"a.dlq": dead_letters(2), "b.dlq": dead_letters(1)},
        publish_errors={"a": UnroutableError([])},
    )
    connect_to(FakeConnection([channel]))

    with caplog.at_level(logging.INFO):
        run_pass(["a", "b"])

    assert [message.routing_key for message in channel.published] == ["b"]
    assert "redrove 0 of 2 message(s) from a.dlq to a" in caplog.text


def test_run_redrive_pass_skips_a_missing_dead_letter_queue_on_a_fresh_channel(
    connect_to: ConnectTo, caplog: pytest.LogCaptureFixture
) -> None:
    closed_by_missing_queue = FakeChannel(
        declare_errors={"a.dlq": ChannelClosedByBroker(404, "NOT_FOUND")}
    )
    fresh = FakeChannel(dead_letters={"b.dlq": dead_letters(1)})
    connection = FakeConnection([closed_by_missing_queue, fresh])
    connect_to(connection)

    with caplog.at_level(logging.WARNING):
        run_pass(["a", "b"])

    assert "a.dlq does not exist; skipping" in caplog.text
    assert connection.opened == [closed_by_missing_queue, fresh]
    assert fresh.calls[0] == ("confirm_delivery", None)
    assert [message.routing_key for message in fresh.published] == ["b"]


def test_run_redrive_pass_propagates_other_broker_errors_and_still_closes(
    connect_to: ConnectTo,
) -> None:
    channel = FakeChannel(
        declare_errors={"a.dlq": ChannelClosedByBroker(403, "ACCESS_REFUSED")}
    )
    connection = FakeConnection([channel])
    connect_to(connection)

    with pytest.raises(ChannelClosedByBroker):
        run_pass(["a", "b"])

    assert connection.close_calls == 1
    assert ("queue_declare", "b.dlq") not in channel.calls


def test_run_redrive_pass_keeps_the_connection_error_when_the_broker_dropped_it(
    connect_to: ConnectTo,
) -> None:
    channel = FakeChannel(
        declare_errors={"a.dlq": AMQPConnectionError("connection lost")}
    )
    connection = FakeConnection([channel])
    connect_to(connection)
    connection.is_open = False

    with pytest.raises(AMQPConnectionError):
        run_pass(["a"])

    assert connection.close_calls == 0


def test_run_redrive_pass_does_not_start_the_next_queue_after_a_stop_request(
    connect_to: ConnectTo,
) -> None:
    channel = FakeChannel(
        dead_letters={"a.dlq": dead_letters(2), "b.dlq": dead_letters(1)}
    )
    connection = FakeConnection([channel])
    connect_to(connection)

    run_pass(
        queues=["a", "b"],
        delay_seconds=5,
        stop_requested=RecordingStopEvent(stop_on_wait=1),
    )

    assert [message.routing_key for message in channel.published] == ["a"]
    assert ("queue_declare", "b.dlq") not in channel.calls
    assert connection.close_calls == 1


def test_run_redrive_pass_with_no_queues_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_to_connect(rabbitmq_url: str) -> FakeConnection:
        raise AssertionError("an empty queue list must not open a connection")

    monkeypatch.setattr(redrive_module, "_open_connection", refuse_to_connect)

    run_pass([])
