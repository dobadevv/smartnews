import logging
import threading
from dataclasses import dataclass
from typing import Protocol

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPConnectionError
from pika.spec import Basic
from pydantic import BaseModel, ValidationError

from smartnews_common.messages import ArticleMessage
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
        method: Basic.Deliver,
        properties: pika.BasicProperties,
        body: bytes,
    ) -> None:
        publisher = Publisher(channel)
        attempt = _attempt_of(properties)
        queue = self._queue
        try:
            message = self._message_type.model_validate_json(body)
        except ValidationError:
            logger.exception("invalid message on %s; dead-lettering it", queue)
            label, destination = "invalid message", dead_letter_queue_name(queue)
        else:
            label = _describe(message)
            logger.info("received message on %s: %s attempt=%d", queue, label, attempt)
            destination = self._process(publisher, message, label, attempt)
        if destination is not None:
            self._republish(publisher, destination, body, attempt + 1, label)
        self._ack(channel, method, label)

    def _process(
        self, publisher: Publisher, message: M, label: str, attempt: int
    ) -> str | None:
        """Run the handler; return where to republish the body, or None when done."""
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
            destination = policy.failure_destination(self._queue, attempt)
            logger.exception(
                "handler failed on %s: %s attempt=%d; routing message to %s",
                self._queue,
                label,
                attempt,
                destination,
            )
            return destination
        return None

    def _republish(
        self,
        publisher: Publisher,
        destination: str,
        body: bytes,
        attempt: int,
        label: str,
    ) -> None:
        try:
            publisher.publish_body(destination, body, attempt)
        except Exception:
            logger.exception(
                "failed to route message on %s: %s to %s",
                self._queue,
                label,
                destination,
            )
            raise
        logger.info("routed message on %s: %s to %s", self._queue, label, destination)

    def _ack(self, channel: BlockingChannel, method: Basic.Deliver, label: str) -> None:
        try:
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception("failed to ack message on %s: %s", self._queue, label)
            raise
        logger.info("acked message on %s: %s", self._queue, label)

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


def _describe(message: BaseModel) -> str:
    if isinstance(message, ArticleMessage):
        return f"article_id={message.article_id}"
    return type(message).__name__


def _attempt_of(properties: pika.BasicProperties) -> int:
    headers = properties.headers or {}
    attempt = headers.get(ATTEMPT_HEADER)
    return attempt if isinstance(attempt, int) else FIRST_ATTEMPT
