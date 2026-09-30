from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import BaseModel

from smartnews_common.messaging.connection import (
    connection_parameters,
    open_confirmed_channel,
)
from smartnews_common.messaging.topology import (
    DEFAULT_RETRY_DELAYS,
    EXCHANGE,
    declare_stage,
)

ATTEMPT_HEADER = "x-attempt"
FIRST_ATTEMPT = 1


class MessagePublisher(Protocol):
    def publish(self, routing_key: str, message: BaseModel) -> None: ...


class Publisher:
    """Publishes on a channel in confirm mode; raises unless the broker confirms."""

    def __init__(self, channel: BlockingChannel) -> None:
        self._channel = channel

    def publish(self, routing_key: str, message: BaseModel) -> None:
        self.publish_body(
            routing_key, message.model_dump_json().encode(), attempt=FIRST_ATTEMPT
        )

    def publish_body(self, routing_key: str, body: bytes, attempt: int) -> None:
        self._channel.basic_publish(
            exchange=EXCHANGE,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                headers={ATTEMPT_HEADER: attempt},
            ),
            # Unroutable messages raise instead of vanishing silently.
            mandatory=True,
        )


@contextmanager
def open_publisher(rabbitmq_url: str, queue: str) -> Iterator[Publisher]:
    connection = pika.BlockingConnection(connection_parameters(rabbitmq_url))
    try:
        channel = open_confirmed_channel(connection)
        declare_stage(channel, queue, DEFAULT_RETRY_DELAYS)
        yield Publisher(channel)
    finally:
        connection.close()
