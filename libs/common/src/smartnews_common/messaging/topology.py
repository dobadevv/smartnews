from datetime import timedelta

from pika.adapters.blocking_connection import BlockingChannel

EXCHANGE = "smartnews"
ARTICLES_FETCHED = "articles.fetched"
ARTICLES_TRANSFORMED = "articles.transformed"
ARTICLES_TO_CRAWL = "articles.crawl"
ARTICLES_CRAWLED = "articles.crawled"
DEFAULT_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)


def retry_queue_name(queue: str, delay: timedelta) -> str:
    return f"{queue}.retry.{_delay_label(delay)}"


def dead_letter_queue_name(queue: str) -> str:
    return f"{queue}.dlq"


def declare_stage(
    channel: BlockingChannel,
    queue: str,
    retry_delays: tuple[timedelta, ...],
    routing_key: str | None = None,
) -> None:
    channel.exchange_declare(exchange=EXCHANGE, exchange_type="direct", durable=True)
    _declare_bound_queue(channel, queue, routing_key=routing_key)
    for delay in retry_delays:
        _declare_bound_queue(
            channel,
            retry_queue_name(queue, delay),
            arguments={
                "x-message-ttl": int(delay.total_seconds() * 1000),
                "x-dead-letter-exchange": EXCHANGE,
                "x-dead-letter-routing-key": queue,
            },
        )
    _declare_bound_queue(channel, dead_letter_queue_name(queue))


def _declare_bound_queue(
    channel: BlockingChannel,
    queue: str,
    routing_key: str | None = None,
    arguments: dict | None = None,
) -> None:
    channel.queue_declare(queue=queue, durable=True, arguments=arguments)
    channel.queue_bind(queue=queue, exchange=EXCHANGE, routing_key=routing_key or queue)


def _delay_label(delay: timedelta) -> str:
    seconds = int(delay.total_seconds())
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"
