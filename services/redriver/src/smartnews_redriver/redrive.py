import logging
import threading
from dataclasses import dataclass

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPChannelError, ChannelClosedByBroker
from smartnews_common.messaging.connection import (
    connection_parameters,
    open_confirmed_channel,
)
from smartnews_common.messaging.publisher import ATTEMPT_HEADER, FIRST_ATTEMPT
from smartnews_common.messaging.topology import dead_letter_queue_name

# The default exchange routes to exactly the queue named by the routing key.
# The `smartnews` exchange would either drop the message as unroutable or fan
# it out to the transformer's queue as well.
DEFAULT_EXCHANGE = ""
NOT_FOUND = 404

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedriveResult:
    snapshot_count: int
    redriven: int


def run_redrive_pass(
    rabbitmq_url: str,
    queues: list[str],
    delay_seconds: float,
    stop_requested: threading.Event,
) -> None:
    if not queues:
        return
    connection = _open_connection(rabbitmq_url)
    try:
        channel = open_confirmed_channel(connection)
        for queue in queues:
            if stop_requested.is_set():
                return
            if not channel.is_open:
                channel = open_confirmed_channel(connection)
            _redrive_and_report(
                channel=channel,
                queue=queue,
                delay_seconds=delay_seconds,
                stop_requested=stop_requested,
            )
    finally:
        # Closing hands unacked messages back to their DLQ. A connection the
        # broker already dropped cannot be closed again, and trying would
        # replace the error that dropped it.
        if connection.is_open:
            connection.close()


def redrive_queue(
    channel: BlockingChannel,
    queue: str,
    delay_seconds: float,
    stop_requested: threading.Event,
) -> RedriveResult:
    dead_letter_queue = dead_letter_queue_name(queue)
    snapshot_count = channel.queue_declare(
        queue=dead_letter_queue, passive=True
    ).method.message_count
    redriven = 0
    for position in range(snapshot_count):
        if position > 0 and _stopped_while_pausing(
            stop_requested=stop_requested, delay_seconds=delay_seconds
        ):
            break
        method, _properties, body = channel.basic_get(
            queue=dead_letter_queue, auto_ack=False
        )
        if method is None:
            break
        try:
            _republish(channel=channel, queue=queue, body=body or b"")
        except AMQPChannelError:
            logger.exception(
                "failed to redrive a message from %s; aborting this queue",
                dead_letter_queue,
            )
            if channel.is_open:
                channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            break
        channel.basic_ack(delivery_tag=method.delivery_tag)
        redriven += 1
    return RedriveResult(snapshot_count=snapshot_count, redriven=redriven)


def _open_connection(rabbitmq_url: str) -> pika.BlockingConnection:
    return pika.BlockingConnection(connection_parameters(rabbitmq_url))


def _redrive_and_report(
    channel: BlockingChannel,
    queue: str,
    delay_seconds: float,
    stop_requested: threading.Event,
) -> None:
    dead_letter_queue = dead_letter_queue_name(queue)
    try:
        result = redrive_queue(
            channel=channel,
            queue=queue,
            delay_seconds=delay_seconds,
            stop_requested=stop_requested,
        )
    except ChannelClosedByBroker as error:
        if error.reply_code != NOT_FOUND:
            raise
        logger.warning("%s does not exist; skipping", dead_letter_queue)
        return
    logger.info(
        "redrove %d of %d message(s) from %s to %s",
        result.redriven,
        result.snapshot_count,
        dead_letter_queue,
        queue,
    )


def _stopped_while_pausing(
    stop_requested: threading.Event, delay_seconds: float
) -> bool:
    if delay_seconds == 0:
        return stop_requested.is_set()
    return stop_requested.wait(delay_seconds)


def _republish(channel: BlockingChannel, queue: str, body: bytes) -> None:
    channel.basic_publish(
        exchange=DEFAULT_EXCHANGE,
        routing_key=queue,
        body=body,
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            headers={ATTEMPT_HEADER: FIRST_ATTEMPT},
        ),
        # With confirms on, an unroutable message raises instead of vanishing.
        mandatory=True,
    )
