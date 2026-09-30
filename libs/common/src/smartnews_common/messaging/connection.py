import pika
from pika.adapters.blocking_connection import BlockingChannel

# A BlockingConnection only services heartbeats between callbacks. The
# transformation handler can block for minutes while Groq waits out rate
# limits, so the heartbeat must outlast the slowest handler or the broker
# drops the connection mid-message.
HEARTBEAT_SECONDS = 600


def connection_parameters(rabbitmq_url: str) -> pika.URLParameters:
    parameters = pika.URLParameters(rabbitmq_url)
    parameters.heartbeat = HEARTBEAT_SECONDS
    return parameters


def open_confirmed_channel(connection: pika.BlockingConnection) -> BlockingChannel:
    channel = connection.channel()
    channel.confirm_delivery()
    return channel
