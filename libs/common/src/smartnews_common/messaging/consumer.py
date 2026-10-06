import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError
from pydantic import BaseModel, ValidationError

from smartnews_common.messaging.connection import (
    connection_parameters,
    open_confirmed_channel,
)
from smartnews_common.messaging.publisher import (
    ATTEMPT_HEADER,
    FIRST_ATTEMPT,
    MessagePublisher,
    Publisher,
)
from smartnews_common.messaging.retry import RetryPolicy
from smartnews_common.messaging.topology import dead_letter_queue_name, declare_stage

RECONNECT_DELAY_SECONDS = 5.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryContext:
    attempt: int
    is_final_attempt: bool
    publisher: MessagePublisher


class MessageHandler[M: BaseModel](Protocol):
    def __call__(self, message: M, context: DeliveryContext) -> None: ...


class Consumer[M: BaseModel]:
    def __init__(
        self,
        rabbitmq_url: str,
        queue: str,
        message_type: type[M],
        handler: MessageHandler[M],
        retry_policy: RetryPolicy | None = None,
        output_queues: tuple[str, ...] = (),
        input_routing_key: str | None = None,
    ) -> None:
        self._rabbitmq_url = rabbitmq_url
        self._queue = queue
        self._message_type = message_type
        self._handler = handler
        self._retry_policy = retry_policy if retry_policy is not None else RetryPolicy()
        self._output_queues = output_queues
        self._input_routing_key = input_routing_key
        self._stop_requested = threading.Event()
        self._connection: pika.BlockingConnection | None = None
        self._channel: BlockingChannel | None = None

    def run(self) -> None:
        while not self._stop_requested.is_set():
            try:
                self._consume_until_stopped()
            except AMQPConnectionError:
                logger.exception(
                    "lost rabbitmq connection while consuming %s; reconnecting in %.0fs",
                    self._queue,
                    RECONNECT_DELAY_SECONDS,
                )
                self._stop_requested.wait(RECONNECT_DELAY_SECONDS)

    def stop(self) -> None:
        self._stop_requested.set()
        connection, channel = self._connection, self._channel
        if connection is not None and channel is not None and connection.is_open:
            connection.add_callback_threadsafe(channel.stop_consuming)

    def declare_topology(self, channel: BlockingChannel) -> None:
        delays = self._retry_policy.delays
        declare_stage(channel, self._queue, delays, routing_key=self._input_routing_key)
        for queue in self._output_queues:
            declare_stage(channel, queue, delays)

    def handle_delivery(
        self,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.BasicProperties,
        body: bytes,
    ) -> None:
        publisher = Publisher(channel)
        attempt = _attempt_of(properties)
        destination = self._process(publisher, body, attempt)
        if destination is not None:
            publisher.publish_body(destination, body, attempt + 1)
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def _process(self, publisher: Publisher, body: bytes, attempt: int) -> str | None:
        """Run the handler; return where to republish the body, or None when done."""
        queue = self._queue
        try:
            message = self._message_type.model_validate_json(body)
        except ValidationError:
            logger.exception("invalid message on %s; dead-lettering it", queue)
            return dead_letter_queue_name(queue)

        policy = self._retry_policy
        context = DeliveryContext(
            attempt=attempt,
            is_final_attempt=policy.is_final_attempt(attempt),
            publisher=publisher,
        )
        try:
            self._handler(message, context)
        # Any handler failure, expected or a bug, goes through the retry
        # ladder so it is retried and finally visible in the DLQ, never lost.
        except Exception:
            destination = policy.failure_destination(queue, attempt)
            logger.exception(
                "handler failed on %s (attempt %d); routing message to %s",
                queue,
                attempt,
                destination,
            )
            return destination
        return None

    def _consume_until_stopped(self) -> None:
        connection = pika.BlockingConnection(connection_parameters(self._rabbitmq_url))
        try:
            channel = open_confirmed_channel(connection)
            self.declare_topology(channel)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=self._queue, on_message_callback=self.handle_delivery
            )
            self._connection, self._channel = connection, channel
            # stop() may have run before the connection was published above.
            if not self._stop_requested.is_set():
                logger.info("consuming %s", self._queue)
                channel.start_consuming()
        finally:
            self._connection, self._channel = None, None
            if connection.is_open:
                connection.close()


def _attempt_of(properties: pika.BasicProperties) -> int:
    headers = properties.headers or {}
    return int(headers.get(ATTEMPT_HEADER, FIRST_ATTEMPT))
