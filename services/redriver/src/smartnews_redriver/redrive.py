import logging
import threading
from dataclasses import dataclass

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPChannelError
from smartnews_common.messaging.publisher import ATTEMPT_HEADER, FIRST_ATTEMPT
from smartnews_common.messaging.topology import dead_letter_queue_name

# The default exchange routes to exactly the queue named by the routing key.
# The `smartnews` exchange would either drop the message as unroutable or fan
# it out to the transformer's queue as well.
DEFAULT_EXCHANGE = ""

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedriveResult:
    snapshot_count: int
    redriven: int


def redrive_queue(
    channel: BlockingChannel,
    queue: str,
    delay_seconds: float,
    stop_requested: threading.Event,
) -> RedriveResult:
    dead_letter_queue = dead_letter_queue_name(queue)
    snapshot_count = channel.queue_declare(
        dead_letter_queue, passive=True
    ).method.message_count
    redriven = 0
    for position in range(snapshot_count):
        if position > 0 and _stopped_while_pausing(
            stop_requested=stop_requested, delay_seconds=delay_seconds
        ):
            break
        method, _properties, body = channel.basic_get(dead_letter_queue, auto_ack=False)
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
