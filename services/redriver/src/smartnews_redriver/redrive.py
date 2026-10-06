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
from smartnews_common.messaging.topology import dead_letter_queue_name

from smartnews_redriver.republish import republish_to_queue, stopped_while_pausing

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
    max_messages_per_run: int,
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
                max_messages_per_run=max_messages_per_run,
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
    max_messages_per_run: int,
) -> RedriveResult:
    dead_letter_queue = dead_letter_queue_name(queue)
    snapshot_count = channel.queue_declare(
        queue=dead_letter_queue, passive=True
    ).method.message_count
    redriven = 0
    for position in range(min(snapshot_count, max_messages_per_run)):
        if position > 0 and stopped_while_pausing(
            stop_requested=stop_requested, delay_seconds=delay_seconds
        ):
            break
        method, _properties, body = channel.basic_get(
            queue=dead_letter_queue, auto_ack=False
        )
        if method is None:
            break
        try:
            republish_to_queue(channel=channel, queue=queue, body=body or b"")
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
    max_messages_per_run: int,
) -> None:
    dead_letter_queue = dead_letter_queue_name(queue)
    try:
        result = redrive_queue(
            channel=channel,
            queue=queue,
            delay_seconds=delay_seconds,
            stop_requested=stop_requested,
            max_messages_per_run=max_messages_per_run,
        )
    except ChannelClosedByBroker as error:
        if error.reply_code != NOT_FOUND:
            raise
        logger.warning("%s does not exist; skipping", dead_letter_queue)
        return
    logger.info(
        "redrove %d of %d message(s) from %s to %s (limit %d)",
        result.redriven,
        result.snapshot_count,
        dead_letter_queue,
        queue,
        max_messages_per_run,
    )
