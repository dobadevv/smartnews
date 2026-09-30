from collections.abc import Callable
from datetime import timedelta

from pika.adapters.blocking_connection import BlockingChannel
from smartnews_common.messaging.publisher import Publisher
from smartnews_common.messaging.topology import (
    dead_letter_queue_name,
    declare_stage,
    retry_queue_name,
)

ONE_SECOND = timedelta(seconds=1)


def test_declare_stage_routes_each_queue_by_its_own_name(
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    declare_stage(rabbitmq_channel, unique_queue, (timedelta(minutes=1),))
    publisher = Publisher(rabbitmq_channel)
    destinations = [
        unique_queue,
        retry_queue_name(unique_queue, timedelta(minutes=1)),
        dead_letter_queue_name(unique_queue),
    ]

    for destination in destinations:
        publisher.publish_body(destination, destination.encode(), attempt=1)

    for destination in destinations:
        _, _, body = wait_for_message(destination)
        assert body == destination.encode()


def test_expired_retry_message_returns_to_the_main_queue(
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    declare_stage(rabbitmq_channel, unique_queue, (ONE_SECOND,))

    Publisher(rabbitmq_channel).publish_body(
        retry_queue_name(unique_queue, ONE_SECOND), b"retry me", attempt=2
    )

    _, properties, body = wait_for_message(unique_queue, timeout=10)
    assert body == b"retry me"
    assert properties.headers["x-attempt"] == 2


def test_declare_stage_is_idempotent(rabbitmq_channel: BlockingChannel, unique_queue: str) -> None:
    declare_stage(rabbitmq_channel, unique_queue, (ONE_SECOND,))
    declare_stage(rabbitmq_channel, unique_queue, (ONE_SECOND,))


def test_declare_stage_can_bind_two_queues_to_the_same_routing_key(
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
) -> None:
    routing_key = f"{unique_queue}.shared"
    other_queue = f"{unique_queue}.other"
    declare_stage(rabbitmq_channel, unique_queue, (), routing_key=routing_key)
    declare_stage(rabbitmq_channel, other_queue, (), routing_key=routing_key)

    Publisher(rabbitmq_channel).publish_body(routing_key, b"fan out", attempt=1)

    _, _, first = wait_for_message(unique_queue)
    _, _, second = wait_for_message(other_queue)
    assert (first, second) == (b"fan out", b"fan out")


def test_expired_retry_message_returns_only_to_its_own_queue_not_a_fan_out_sibling(
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    wait_for_message: Callable,
    message_count: Callable[[str], int],
) -> None:
    """A queue declared with a routing_key override (fan-out) must still get
    its own expired retry messages back, without also redelivering them to a
    sibling queue that happens to share that same routing_key.
    """
    routing_key = f"{unique_queue}.shared"
    sibling_queue = f"{unique_queue}.sibling"
    declare_stage(rabbitmq_channel, unique_queue, (ONE_SECOND,), routing_key=routing_key)
    declare_stage(rabbitmq_channel, sibling_queue, (), routing_key=routing_key)

    Publisher(rabbitmq_channel).publish_body(
        retry_queue_name(unique_queue, ONE_SECOND), b"retry me", attempt=2
    )

    _, properties, body = wait_for_message(unique_queue, timeout=10)
    assert body == b"retry me"
    assert properties.headers["x-attempt"] == 2
    assert message_count(sibling_queue) == 0
