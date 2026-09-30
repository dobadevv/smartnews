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
