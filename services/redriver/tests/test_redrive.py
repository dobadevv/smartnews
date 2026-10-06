import logging
import threading
from dataclasses import dataclass
from typing import cast

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import ChannelClosedByBroker, NackError, UnroutableError
from pika.frame import Method
from pika.spec import Basic, Queue
from smartnews_redriver.redrive import RedriveResult, redrive_queue

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
) -> RedriveResult:
    return redrive_queue(
        channel=as_channel(channel),
        queue=MAIN_QUEUE,
        delay_seconds=delay_seconds,
        stop_requested=stop_requested or RecordingStopEvent(),
    )


def test_redrive_queue_redrives_at_most_the_snapshot_count() -> None:
    channel = FakeChannel(
        dead_letters={DEAD_LETTER_QUEUE: dead_letters(3)},
        declared_counts={DEAD_LETTER_QUEUE: 2},
    )

    result = redrive(channel)

    assert result == RedriveResult(snapshot_count=2, redriven=2)
    assert len(channel.calls_named("basic_get")) == 2


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
        channel, delay_seconds=delay_seconds, stop_requested=stop_requested
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

    result = redrive(channel, delay_seconds=5, stop_requested=stop_requested)

    assert result == RedriveResult(snapshot_count=3, redriven=1)
    assert channel.calls_named("basic_ack") == [1]
    assert len(channel.calls_named("basic_get")) == 1


def test_redrive_queue_without_a_delay_still_stops_between_messages() -> None:
    channel = FakeChannel(dead_letters={DEAD_LETTER_QUEUE: dead_letters(3)})
    stop_requested = RecordingStopEvent()
    stop_requested.set()

    result = redrive(channel, delay_seconds=0, stop_requested=stop_requested)

    assert result == RedriveResult(snapshot_count=3, redriven=1)
    assert stop_requested.waits == []
