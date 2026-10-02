import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

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
from smartnews_common.messaging.retry import RetryPolicy
from smartnews_common.messaging.topology import (
    ARTICLES_CRAWLED,
    ARTICLES_FETCHED,
    ARTICLES_TO_CRAWL,
    ARTICLES_TRANSFORMED,
    DEFAULT_RETRY_DELAYS,
    dead_letter_queue_name,
    declare_stage,
    retry_queue_name,
)
from smartnews_common.models import Article, Transformation
from smartnews_crawler.config import CrawlerConfig
from smartnews_crawler.extraction.registry import ExtractorRegistry
from smartnews_crawler.fetching.base import FetchError
from smartnews_crawler.handler import CrawlerHandler, CrawlerHandlerDeps
from smartnews_crawler.recording import DatabaseContentRecorder
from smartnews_fetcher.config import FetcherConfig, SourceConfig
from smartnews_fetcher.cycle import CycleDeps, run_cycle
from smartnews_notifier.handler import NotificationHandler, NotificationHandlerDeps
from smartnews_notifier.ledger import DatabaseDeliveryLedger
from smartnews_transformer.handler import (
    TransformationHandler,
    TransformationHandlerDeps,
)
from smartnews_transformer.recording import DatabaseTransformationRecorder
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
    declare_stage(rabbitmq_channel, ARTICLES_TO_CRAWL, DEFAULT_RETRY_DELAYS, routing_key=ARTICLES_FETCHED)
    for queue in (ARTICLES_FETCHED, ARTICLES_TRANSFORMED, ARTICLES_CRAWLED):
        declare_stage(rabbitmq_channel, queue, DEFAULT_RETRY_DELAYS)
    for queue in (ARTICLES_FETCHED, ARTICLES_TRANSFORMED, ARTICLES_TO_CRAWL, ARTICLES_CRAWLED):
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


class FixedPageFetcher:
    def __init__(self, html: str) -> None:
        self._html = html

    def fetch(self, url: str) -> str:
        return self._html


ARTICLE_HTML = (
    "<html><body><article><p>"
    "The full article body crawled from the source page, long enough for "
    "trafilatura's heuristics to treat it as the main content block reliably "
    "across a couple of sentences of genuine prose."
    "</p></article></body></html>"
)


def test_a_fetched_article_fans_out_to_transformation_and_crawler(
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
            NotificationHandlerDeps(notifiers=[notifier], ledger=DatabaseDeliveryLedger(engine))
        ),
        expected=1,
    )
    crawler = CountingHandler(
        CrawlerHandler(
            CrawlerHandlerDeps(
                fetcher=FixedPageFetcher(ARTICLE_HTML),
                extractors=ExtractorRegistry(CrawlerConfig()),
                recorder=DatabaseContentRecorder(engine),
            )
        ),
        expected=1,
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
    start_consumer(
        request,
        ConsumerDeps(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_TO_CRAWL,
            message_type=ArticleFetched,
            handler=crawler,
            input_routing_key=ARTICLES_FETCHED,
            output_queues=(ARTICLES_CRAWLED,),
        ),
    )
    cycle = CycleDeps(
        config=FetcherConfig(sources=[SourceConfig(name="example-blog", url="unused", max_posts=1)]),
        fetcher=SingleArticleFetcher(),
        engine=engine,
        rabbitmq_url=rabbitmq_url,
    )

    run_cycle(cycle)

    assert transformation.done.wait(TIMEOUT_SECONDS)
    assert notification.done.wait(TIMEOUT_SECONDS)
    assert crawler.done.wait(TIMEOUT_SECONDS)
    article_id = scalar(engine, "SELECT id FROM articles")
    assert scalar(engine, "SELECT title FROM article_transformations") == "[vi] Hello World"
    assert scalar(engine, "SELECT channel FROM article_deliveries") == "discord"
    with engine.connect() as connection:
        content = connection.execute(
            text("SELECT content FROM article_contents WHERE article_id = :id"),
            {"id": article_id},
        ).scalar_one()
    assert "article body crawled" in content


class AlwaysFailingPageFetcher:
    def fetch(self, url: str) -> str:
        raise FetchError(f"blocked: {url}")


def test_crawler_failure_does_not_block_transformation_or_notification(
    engine: Engine,
    rabbitmq_url: str,
    rabbitmq_channel: BlockingChannel,
    clean_queues: None,
    request: pytest.FixtureRequest,
    wait_for_message: Callable,
) -> None:
    short_delay = timedelta(seconds=1)
    declare_stage(rabbitmq_channel, ARTICLES_TO_CRAWL, (short_delay,), routing_key=ARTICLES_FETCHED)
    rabbitmq_channel.queue_purge(retry_queue_name(ARTICLES_TO_CRAWL, short_delay))

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
            NotificationHandlerDeps(notifiers=[notifier], ledger=DatabaseDeliveryLedger(engine))
        ),
        expected=1,
    )
    crawler_handler = CrawlerHandler(
        CrawlerHandlerDeps(
            fetcher=AlwaysFailingPageFetcher(),
            extractors=ExtractorRegistry(CrawlerConfig()),
            recorder=DatabaseContentRecorder(engine),
        )
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
    start_consumer(
        request,
        ConsumerDeps(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_TO_CRAWL,
            message_type=ArticleFetched,
            handler=crawler_handler,
            input_routing_key=ARTICLES_FETCHED,
            output_queues=(ARTICLES_CRAWLED,),
            retry_policy=RetryPolicy(delays=(short_delay,)),
        ),
    )
    cycle = CycleDeps(
        config=FetcherConfig(sources=[SourceConfig(name="example-blog", url="unused", max_posts=1)]),
        fetcher=SingleArticleFetcher(),
        engine=engine,
        rabbitmq_url=rabbitmq_url,
    )

    run_cycle(cycle)

    assert transformation.done.wait(TIMEOUT_SECONDS)
    assert notification.done.wait(TIMEOUT_SECONDS)
    _, _, dead = wait_for_message(dead_letter_queue_name(ARTICLES_TO_CRAWL), timeout=TIMEOUT_SECONDS)
    assert ArticleFetched.model_validate_json(dead).title == "Hello World"
    assert scalar(engine, "SELECT title FROM article_transformations") == "[vi] Hello World"
    assert scalar(engine, "SELECT channel FROM article_deliveries") == "discord"
    with engine.connect() as connection:
        row_exists = connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM article_contents)")
        ).scalar_one()
    assert row_exists is False
