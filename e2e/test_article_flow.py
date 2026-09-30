import threading
from datetime import UTC, datetime

import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pydantic import BaseModel
from smartnews_common.messages import ArticleFetched, ArticleTransformed
from smartnews_common.messaging.consumer import (
    Consumer,
    ConsumerDeps,
    DeliveryContext,
    MessageHandler,
)
from smartnews_common.messaging.publisher import Publisher
from smartnews_common.messaging.topology import (
    ARTICLES_FETCHED,
    ARTICLES_TRANSFORMED,
    DEFAULT_RETRY_DELAYS,
    dead_letter_queue_name,
    declare_stage,
    retry_queue_name,
)
from smartnews_common.models import Article, Transformation
from smartnews_fetcher.config import FetcherConfig, SourceConfig
from smartnews_fetcher.cycle import CycleDeps, run_cycle
from smartnews_notification.handler import NotificationHandler, NotificationHandlerDeps
from smartnews_notification.ledger import DatabaseDeliveryLedger
from smartnews_transformation.handler import (
    TransformationHandler,
    TransformationHandlerDeps,
)
from smartnews_transformation.recording import DatabaseTransformationRecorder
from sqlalchemy import Engine, text

TIMEOUT_SECONDS = 15
FEED_ARTICLE = Article(
    title="Hello World",
    url="https://example.com/hello",
    source="example-blog",
    published_at=datetime.now(UTC),
    summary="An introductory post",
)
TRANSLATION = Transformation(title="[vi] Hello World", summary="Tóm tắt", language="vi")


class SingleArticleFetcher:
    def fetch(self, source: SourceConfig) -> list[Article]:
        return [FEED_ARTICLE]


class FixedTranslationFilter:
    def transform(self, article: Article) -> Transformation:
        return TRANSLATION


class RecordingNotifier:
    channel = "discord"

    def __init__(self) -> None:
        self.sent: list[Article] = []

    def send(self, article: Article) -> None:
        self.sent.append(article)


class CountingHandler[M: BaseModel]:
    """Delegates to a real handler and signals once `expected` messages were handled."""

    def __init__(self, inner: MessageHandler[M], expected: int) -> None:
        self._inner = inner
        self._expected = expected
        self._handled = 0
        self.done = threading.Event()

    def __call__(self, message: M, context: DeliveryContext) -> None:
        self._inner(message, context)
        self._handled += 1
        if self._handled >= self._expected:
            self.done.set()


@pytest.fixture
def clean_queues(rabbitmq_channel: BlockingChannel) -> None:
    for queue in (ARTICLES_FETCHED, ARTICLES_TRANSFORMED):
        declare_stage(rabbitmq_channel, queue, DEFAULT_RETRY_DELAYS)
        retry_queues = [retry_queue_name(queue, delay) for delay in DEFAULT_RETRY_DELAYS]
        for name in (queue, dead_letter_queue_name(queue), *retry_queues):
            rabbitmq_channel.queue_purge(name)


def start_consumer(request: pytest.FixtureRequest, deps: ConsumerDeps) -> None:
    consumer = Consumer(deps)
    thread = threading.Thread(target=consumer.run)
    thread.start()

    def stop() -> None:
        consumer.stop()
        thread.join(timeout=TIMEOUT_SECONDS)

    request.addfinalizer(stop)


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def test_one_feed_entry_is_translated_and_delivered_exactly_once(
    engine: Engine,
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    clean_queues: None,
    request: pytest.FixtureRequest,
) -> None:
    notifier = RecordingNotifier()
    transformation = CountingHandler(
        TransformationHandler(
            TransformationHandlerDeps(
                article_filter=FixedTranslationFilter(),
                recorder=DatabaseTransformationRecorder(engine),
            )
        ),
        expected=1,
    )
    notification = CountingHandler(
        NotificationHandler(
            NotificationHandlerDeps(
                notifiers=[notifier], ledger=DatabaseDeliveryLedger(engine)
            )
        ),
        expected=2,
    )
    start_consumer(
        request,
        ConsumerDeps(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_FETCHED,
            message_type=ArticleFetched,
            handler=transformation,
            output_queues=(ARTICLES_TRANSFORMED,),
        ),
    )
    start_consumer(
        request,
        ConsumerDeps(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_TRANSFORMED,
            message_type=ArticleTransformed,
            handler=notification,
        ),
    )
    cycle = CycleDeps(
        config=FetcherConfig(
            fetch_interval_minutes=1,
            sources=[SourceConfig(name="example-blog", url="unused", max_posts=1)],
        ),
        fetcher=SingleArticleFetcher(),
        engine=engine,
        rabbitmq_url=rabbitmq_url,
    )

    first_cycle = run_cycle(cycle)
    second_cycle = run_cycle(cycle)
    assert transformation.done.wait(TIMEOUT_SECONDS)
    article_id = scalar(engine, "SELECT id FROM articles")
    # A redelivered message must not post a second time.
    Publisher(rabbitmq_channel).publish(
        ARTICLES_TRANSFORMED,
        ArticleTransformed.translated(
            ArticleFetched.from_article(FEED_ARTICLE, article_id), TRANSLATION
        ),
    )
    assert notification.done.wait(TIMEOUT_SECONDS)

    assert (first_cycle, second_cycle) == (1, 0)
    assert [article.title for article in notifier.sent] == ["[vi] Hello World"]
    assert scalar(engine, "SELECT title FROM article_transformations") == "[vi] Hello World"
    assert scalar(engine, "SELECT channel FROM article_deliveries") == "discord"
