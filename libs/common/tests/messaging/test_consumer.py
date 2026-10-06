import threading
from collections.abc import Callable
from datetime import timedelta
from typing import TypedDict, Unpack

import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic
from pydantic import BaseModel
from smartnews_common.messaging.consumer import Consumer, DeliveryContext
from smartnews_common.messaging.publisher import Publisher
from smartnews_common.messaging.retry import RetryPolicy
from smartnews_common.messaging.topology import dead_letter_queue_name, retry_queue_name

ONE_MINUTE = timedelta(minutes=1)


class Ping(BaseModel):
    value: str


class RecordingHandler:
    def __init__(self, *, error: Exception | None = None, expected_calls: int = 1) -> None:
        self.calls: list[tuple[Ping, DeliveryContext]] = []
        self.done = threading.Event()
        self._error = error
        self._expected_calls = expected_calls

    def __call__(self, message: Ping, context: DeliveryContext) -> None:
        self.calls.append((message, context))
        if len(self.calls) >= self._expected_calls:
            self.done.set()
        if self._error is not None:
            raise self._error


class ConsumerOverrides(TypedDict, total=False):
    output_queues: tuple[str, ...]
    input_routing_key: str | None


def make_consumer(
    rabbitmq_url: str, queue: str, handler: RecordingHandler, **overrides: Unpack[ConsumerOverrides]
) -> Consumer[Ping]:
    return Consumer(
        rabbitmq_url=rabbitmq_url,
        queue=queue,
        message_type=Ping,
        handler=handler,
        retry_policy=RetryPolicy(delays=(ONE_MINUTE,)),
        **overrides,
    )


def deliver(
    consumer: Consumer[Ping], channel: BlockingChannel, queue: str, body: bytes, attempt: int = 1
) -> None:
    Publisher(channel).publish_body(queue, body, attempt=attempt)
    method, properties, received = None, None, b""
    for _ in range(200):
        method, properties, received = channel.basic_get(queue)
        if method is not None:
            break
        channel.connection.process_data_events(time_limit=0.05)
    assert method is not None, f"message never reached {queue}"
    assert properties is not None and received is not None
    # basic_get answers with GetOk; the consumer is driven by push deliveries.
    delivery = Basic.Deliver(
        delivery_tag=method.delivery_tag, exchange=method.exchange, routing_key=method.routing_key
    )
    consumer.handle_delivery(channel, delivery, properties, received)


def test_handle_delivery_passes_the_decoded_message_and_first_attempt_context(
    rabbitmq_url: str, rabbitmq_channel: BlockingChannel, unique_queue: str
) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(rabbitmq_url, unique_queue, handler)
    consumer.declare_topology(rabbitmq_channel)

    deliver(consumer, rabbitmq_channel, unique_queue, Ping(value="a").model_dump_json().encode())

    [(message, context)] = handler.calls
    assert message == Ping(value="a")
    assert (context.attempt, context.is_final_attempt) == (1, False)


def test_handle_delivery_routes_a_failed_message_to_the_retry_queue_with_the_next_attempt(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    consumer = make_consumer(rabbitmq_url, unique_queue, RecordingHandler(error=RuntimeError("boom")))
    consumer.declare_topology(rabbitmq_channel)
    body = Ping(value="a").model_dump_json().encode()

    deliver(consumer, rabbitmq_channel, unique_queue, body)

    _, properties, retried = wait_for_message(retry_queue_name(unique_queue, ONE_MINUTE))
    assert retried == body
    assert properties.headers["x-attempt"] == 2


def test_handle_delivery_dead_letters_a_message_that_fails_its_final_attempt(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    handler = RecordingHandler(error=RuntimeError("boom"))
    consumer = make_consumer(rabbitmq_url, unique_queue, handler)
    consumer.declare_topology(rabbitmq_channel)
    body = Ping(value="a").model_dump_json().encode()

    deliver(consumer, rabbitmq_channel, unique_queue, body, attempt=2)

    [(_, context)] = handler.calls
    assert context.is_final_attempt is True
    _, _, dead = wait_for_message(dead_letter_queue_name(unique_queue))
    assert dead == body


def test_handle_delivery_dead_letters_an_invalid_payload_without_calling_the_handler(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
    message_count: Callable[[str], int],
) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(rabbitmq_url, unique_queue, handler)
    consumer.declare_topology(rabbitmq_channel)

    deliver(consumer, rabbitmq_channel, unique_queue, b"not json")

    assert handler.calls == []
    _, _, dead = wait_for_message(dead_letter_queue_name(unique_queue))
    assert dead == b"not json"
    assert message_count(retry_queue_name(unique_queue, ONE_MINUTE)) == 0


def test_declare_topology_also_declares_output_queues(
    rabbitmq_url: str, rabbitmq_channel: BlockingChannel, unique_queue: str
) -> None:
    output_queue = f"{unique_queue}.out"
    consumer = make_consumer(
        rabbitmq_url, unique_queue, RecordingHandler(), output_queues=(output_queue,)
    )

    consumer.declare_topology(rabbitmq_channel)

    rabbitmq_channel.queue_declare(output_queue, passive=True)
    rabbitmq_channel.queue_declare(dead_letter_queue_name(output_queue), passive=True)


def test_run_acks_each_message_and_stops_when_asked(
    rabbitmq_url: str, rabbitmq_channel: BlockingChannel, unique_queue: str
) -> None:
    handler = RecordingHandler(expected_calls=2)
    consumer = make_consumer(rabbitmq_url, unique_queue, handler)
    consumer.declare_topology(rabbitmq_channel)
    publisher = Publisher(rabbitmq_channel)
    thread = threading.Thread(target=consumer.run)
    thread.start()

    publisher.publish(unique_queue, Ping(value="first"))
    publisher.publish(unique_queue, Ping(value="second"))

    # prefetch=1: the second message is only delivered after the first is acked.
    handled_both = handler.done.wait(timeout=10)
    consumer.stop()
    thread.join(timeout=10)
    assert handled_both
    assert [message.value for message, _ in handler.calls] == ["first", "second"]
    assert not thread.is_alive()


def test_stop_before_run_returns_immediately(rabbitmq_url: str, unique_queue: str) -> None:
    consumer = make_consumer(rabbitmq_url, unique_queue, RecordingHandler())

    consumer.stop()
    consumer.run()


@pytest.mark.parametrize("error", [RuntimeError("bug"), ValueError("bad value")])
def test_handle_delivery_retries_any_handler_exception(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
    error: Exception,
) -> None:
    consumer = make_consumer(rabbitmq_url, unique_queue, RecordingHandler(error=error))
    consumer.declare_topology(rabbitmq_channel)

    deliver(consumer, rabbitmq_channel, unique_queue, Ping(value="a").model_dump_json().encode())

    wait_for_message(retry_queue_name(unique_queue, ONE_MINUTE))


def test_declare_topology_binds_the_input_queue_to_a_custom_routing_key(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    routing_key = f"{unique_queue}.shared"
    consumer = make_consumer(
        rabbitmq_url, unique_queue, RecordingHandler(), input_routing_key=routing_key
    )
    consumer.declare_topology(rabbitmq_channel)

    Publisher(rabbitmq_channel).publish_body(routing_key, b"fan out", attempt=1)

    _, _, body = wait_for_message(unique_queue)
    assert body == b"fan out"
