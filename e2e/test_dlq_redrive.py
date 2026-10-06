import threading
import uuid
from collections.abc import Callable

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.topology import (
    ARTICLES_FETCHED,
    ARTICLES_TO_CRAWL,
    DEFAULT_RETRY_DELAYS,
    dead_letter_queue_name,
    declare_stage,
    retry_queue_name,
)
from smartnews_redriver.redrive import run_redrive_pass

CRAWL_DEAD_LETTER_QUEUE = dead_letter_queue_name(ARTICLES_TO_CRAWL)
FINAL_ATTEMPT = 4


@pytest.fixture
def clean_crawl_queues(rabbitmq_channel: BlockingChannel) -> None:
    declare_stage(
        channel=rabbitmq_channel,
        queue=ARTICLES_TO_CRAWL,
        retry_delays=DEFAULT_RETRY_DELAYS,
        routing_key=ARTICLES_FETCHED,
    )
    declare_stage(
        channel=rabbitmq_channel,
        queue=ARTICLES_FETCHED,
        retry_delays=DEFAULT_RETRY_DELAYS,
    )
    # Retry queues too: a leftover would TTL back into a main queue mid-test.
    retry_queues = [
        retry_queue_name(queue=queue, delay=delay)
        for queue in (ARTICLES_TO_CRAWL, ARTICLES_FETCHED)
        for delay in DEFAULT_RETRY_DELAYS
    ]
    for queue in (
        ARTICLES_TO_CRAWL,
        CRAWL_DEAD_LETTER_QUEUE,
        ARTICLES_FETCHED,
        *retry_queues,
    ):
        rabbitmq_channel.queue_purge(queue)


def fetched_body(article_id: int) -> bytes:
    return (
        ArticleFetched(
            article_id=article_id,
            hash_url=f"hash-{article_id}",
            url=f"https://example.com/articles/{article_id}",
            title="Rate limited article",
            summary=None,
            published_at=None,
            source="example-blog",
            thumbnail=None,
            category=None,
        )
        .model_dump_json()
        .encode()
    )


def dead_letter(channel: BlockingChannel, queue: str, body: bytes) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=body,
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=pika.DeliveryMode.Persistent,
            headers={"x-attempt": FINAL_ATTEMPT},
        ),
        mandatory=True,
    )


def redrive(rabbitmq_url: str, queues: list[str], delay_seconds: float = 0) -> None:
    run_redrive_pass(
        rabbitmq_url=rabbitmq_url,
        queues=queues,
        delay_seconds=delay_seconds,
        stop_requested=threading.Event(),
    )


def test_a_dead_lettered_crawl_goes_back_to_the_crawler_only_as_a_first_attempt(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    clean_crawl_queues: None,
    wait_for_message: Callable[..., tuple],
    message_count: Callable[[str], int],
) -> None:
    body = fetched_body(1)
    dead_letter(channel=rabbitmq_channel, queue=CRAWL_DEAD_LETTER_QUEUE, body=body)

    redrive(rabbitmq_url=rabbitmq_url, queues=[ARTICLES_TO_CRAWL])

    _, properties, received = wait_for_message(ARTICLES_TO_CRAWL)
    assert received == body
    assert properties.headers == {"x-attempt": 1}
    assert message_count(CRAWL_DEAD_LETTER_QUEUE) == 0
    assert message_count(ARTICLES_FETCHED) == 0


def test_redrive_keeps_the_dead_letter_order_with_a_delay_between_messages(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    clean_crawl_queues: None,
    wait_for_message: Callable[..., tuple],
) -> None:
    bodies = [fetched_body(1), fetched_body(2)]
    for body in bodies:
        dead_letter(channel=rabbitmq_channel, queue=CRAWL_DEAD_LETTER_QUEUE, body=body)

    redrive(rabbitmq_url=rabbitmq_url, queues=[ARTICLES_TO_CRAWL], delay_seconds=0.05)

    received = [wait_for_message(ARTICLES_TO_CRAWL)[2] for _ in bodies]
    assert received == bodies


def test_a_missing_dead_letter_queue_is_skipped_and_the_next_queue_redriven(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    clean_crawl_queues: None,
    wait_for_message: Callable[..., tuple],
) -> None:
    body = fetched_body(1)
    dead_letter(channel=rabbitmq_channel, queue=CRAWL_DEAD_LETTER_QUEUE, body=body)

    redrive(
        rabbitmq_url=rabbitmq_url,
        queues=[f"missing.{uuid.uuid4().hex}", ARTICLES_TO_CRAWL],
    )

    assert wait_for_message(ARTICLES_TO_CRAWL)[2] == body


def test_a_message_whose_main_queue_is_missing_stays_in_the_dead_letter_queue(
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    unique_queue: str,
    message_count: Callable[[str], int],
) -> None:
    orphan_dead_letter_queue = dead_letter_queue_name(unique_queue)
    rabbitmq_channel.queue_declare(queue=orphan_dead_letter_queue, durable=True)
    dead_letter(
        channel=rabbitmq_channel,
        queue=orphan_dead_letter_queue,
        body=fetched_body(1),
    )

    redrive(rabbitmq_url=rabbitmq_url, queues=[unique_queue])

    assert message_count(orphan_dead_letter_queue) == 1
