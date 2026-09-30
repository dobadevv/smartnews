from collections.abc import Callable

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import BaseModel
from smartnews_common.messaging.publisher import Publisher, open_publisher
from smartnews_common.messaging.topology import DEFAULT_RETRY_DELAYS, declare_stage


class Ping(BaseModel):
    value: str


def test_publish_sends_persistent_json_marked_as_first_attempt(
    rabbitmq_channel: BlockingChannel, unique_queue: str, wait_for_message: Callable
) -> None:
    declare_stage(rabbitmq_channel, unique_queue, DEFAULT_RETRY_DELAYS)

    Publisher(rabbitmq_channel).publish(unique_queue, Ping(value="hello"))

    _, properties, body = wait_for_message(unique_queue)
    assert Ping.model_validate_json(body) == Ping(value="hello")
    assert properties.delivery_mode == pika.DeliveryMode.Persistent.value
    assert properties.content_type == "application/json"
    assert properties.headers == {"x-attempt": 1}


def test_publish_raises_when_no_queue_is_bound_to_the_routing_key(
    rabbitmq_channel: BlockingChannel, unique_queue: str
) -> None:
    declare_stage(rabbitmq_channel, unique_queue, DEFAULT_RETRY_DELAYS)

    with pytest.raises(pika.exceptions.UnroutableError):
        Publisher(rabbitmq_channel).publish(f"{unique_queue}.missing", Ping(value="lost"))


def test_open_publisher_declares_the_stage_and_publishes(
    rabbitmq_url: str, unique_queue: str, wait_for_message: Callable
) -> None:
    with open_publisher(rabbitmq_url, unique_queue) as publisher:
        publisher.publish(unique_queue, Ping(value="via context"))

    _, _, body = wait_for_message(unique_queue)
    assert Ping.model_validate_json(body) == Ping(value="via context")
