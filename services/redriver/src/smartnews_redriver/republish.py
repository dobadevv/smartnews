import threading

import pika
from pika.adapters.blocking_connection import BlockingChannel
from smartnews_common.messaging.publisher import ATTEMPT_HEADER, FIRST_ATTEMPT

# The default exchange routes to exactly the queue named by the routing key.
# The `smartnews` exchange would either drop the message as unroutable or fan
# it out to every other queue bound to the same routing key as well.
DEFAULT_EXCHANGE = ""


def republish_to_queue(channel: BlockingChannel, queue: str, body: bytes) -> None:
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


def stopped_while_pausing(
    stop_requested: threading.Event, delay_seconds: float
) -> bool:
    if delay_seconds == 0:
        return stop_requested.is_set()
    return stop_requested.wait(delay_seconds)
