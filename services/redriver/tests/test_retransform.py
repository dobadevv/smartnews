import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import pika
import pytest
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import (
    AMQPConnectionError,
    ChannelClosedByBroker,
    ConnectionWrongStateError,
    NackError,
    UnroutableError,
)
from smartnews_common.db.generated.articles import ListUntransformedArticlesRow
from smartnews_common.messages import ArticleFetched
from smartnews_redriver import retransform as retransform_module
from smartnews_redriver.retransform import (
    republish_articles,
    run_retransform_pass,
    select_untransformed_articles,
)
from sqlalchemy import Engine
from sqlalchemy.pool import QueuePool

PUBLISHED_AT = datetime(2026, 10, 1, 7, 0, tzinfo=UTC)
FIRST_ATTEMPT_PROPERTIES = pika.BasicProperties(
    content_type="application/json",
    delivery_mode=pika.DeliveryMode.Persistent,
    headers={"x-attempt": 1},
)


@dataclass(frozen=True)
class PublishedMessage:
    exchange: str
    routing_key: str
    body: bytes
    properties: pika.BasicProperties
    mandatory: bool


class FakeChannel:
    """Stands in for a confirmed BlockingChannel; publish number `failing_publish` raises."""

    def __init__(
        self,
        failing_publish: int | None = None,
        publish_error: Exception | None = None,
    ) -> None:
        self._failing_publish = failing_publish
        self._publish_error = publish_error
        self.publish_attempts = 0
        self.confirm_calls = 0
        self.is_open = True
        self.published: list[PublishedMessage] = []

    def confirm_delivery(self) -> None:
        self.confirm_calls += 1

    def basic_publish(
        self,
        exchange: str,
        routing_key: str,
        body: bytes,
        properties: pika.BasicProperties,
        mandatory: bool,
    ) -> None:
        self.publish_attempts += 1
        if self.publish_attempts == self._failing_publish:
            assert self._publish_error is not None
            raise self._publish_error
        self.published.append(
            PublishedMessage(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                properties=properties,
                mandatory=mandatory,
            )
        )


class FakeConnection:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel
        self.is_open = True
        self.close_calls = 0

    def channel(self) -> FakeChannel:
        return self._channel

    def close(self) -> None:
        if not self.is_open:
            raise ConnectionWrongStateError("connection already closed")
        self.close_calls += 1
        self.is_open = False


class RecordingStopEvent(threading.Event):
    """Records requested waits instead of sleeping; sets itself on wait number `stop_on_wait`."""

    def __init__(self, stop_on_wait: int | None = None) -> None:
        super().__init__()
        self.waits: list[float | None] = []
        self._stop_on_wait = stop_on_wait

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        if len(self.waits) == self._stop_on_wait:
            self.set()
        return self.is_set()


def article_row(article_id: int) -> ListUntransformedArticlesRow:
    return ListUntransformedArticlesRow(
        id=article_id,
        hash_url=f"hash-{article_id}",
        url=f"https://example.com/{article_id}",
        title=f"Title {article_id}",
        summary=f"Summary {article_id}",
        published_at=PUBLISHED_AT,
        source="example-blog",
        thumbnail=f"https://example.com/{article_id}.png",
        category="architecture",
    )


def sparse_article_row(article_id: int) -> ListUntransformedArticlesRow:
    return ListUntransformedArticlesRow(
        id=article_id,
        hash_url=f"hash-{article_id}",
        url=f"https://example.com/{article_id}",
        title=f"Title {article_id}",
        summary=None,
        published_at=None,
        source="example-blog",
        thumbnail=None,
        category=None,
    )


def article_rows(count: int) -> list[ListUntransformedArticlesRow]:
    return [article_row(article_id) for article_id in range(1, count + 1)]


def published_article_ids(channel: FakeChannel) -> list[int]:
    return [
        ArticleFetched.model_validate_json(message.body).article_id
        for message in channel.published
    ]


def republish(
    channel: FakeChannel,
    articles: list[ListUntransformedArticlesRow],
    delay_seconds: float = 0,
    stop_requested: threading.Event | None = None,
) -> int:
    return republish_articles(
        channel=cast(BlockingChannel, channel),
        articles=articles,
        delay_seconds=delay_seconds,
        stop_requested=stop_requested or RecordingStopEvent(),
    )


@pytest.mark.parametrize(
    ("row", "expected_message"),
    [
        pytest.param(
            article_row(7),
            ArticleFetched(
                article_id=7,
                hash_url="hash-7",
                url="https://example.com/7",
                title="Title 7",
                summary="Summary 7",
                published_at=PUBLISHED_AT,
                source="example-blog",
                thumbnail="https://example.com/7.png",
                category="architecture",
            ),
            id="every-column-set",
        ),
        pytest.param(
            sparse_article_row(8),
            ArticleFetched(
                article_id=8,
                hash_url="hash-8",
                url="https://example.com/8",
                title="Title 8",
                summary=None,
                published_at=None,
                source="example-blog",
                thumbnail=None,
                category=None,
            ),
            id="optional-columns-null",
        ),
    ],
)
def test_republish_articles_sends_each_row_as_an_article_fetched_message(
    row: ListUntransformedArticlesRow, expected_message: ArticleFetched
) -> None:
    channel = FakeChannel()

    republished = republish(channel=channel, articles=[row])

    assert republished == 1
    assert [message.body for message in channel.published] == [
        expected_message.model_dump_json().encode()
    ]


def test_republish_articles_publishes_only_to_articles_fetched_as_a_persistent_first_attempt() -> None:
    channel = FakeChannel()

    republish(channel=channel, articles=article_rows(2))

    assert [
        (message.exchange, message.routing_key, message.properties, message.mandatory)
        for message in channel.published
    ] == [("", "articles.fetched", FIRST_ATTEMPT_PROPERTIES, True)] * 2
    assert published_article_ids(channel) == [1, 2]


@pytest.mark.parametrize(
    ("article_count", "delay_seconds", "expected_waits"),
    [
        pytest.param(1, 5.0, [], id="single-article-never-waits"),
        pytest.param(3, 5.0, [5.0, 5.0], id="waits-between-articles-only"),
        pytest.param(3, 0.0, [], id="zero-delay-never-waits"),
    ],
)
def test_republish_articles_waits_the_delay_between_articles(
    article_count: int, delay_seconds: float, expected_waits: list[float]
) -> None:
    channel = FakeChannel()
    stop_requested = RecordingStopEvent()

    republished = republish(
        channel=channel,
        articles=article_rows(article_count),
        delay_seconds=delay_seconds,
        stop_requested=stop_requested,
    )

    assert republished == article_count
    assert stop_requested.waits == expected_waits


def test_republish_articles_stops_when_stop_is_requested_during_a_delay() -> None:
    channel = FakeChannel()

    republished = republish(
        channel=channel,
        articles=article_rows(3),
        delay_seconds=5,
        stop_requested=RecordingStopEvent(stop_on_wait=1),
    )

    assert republished == 1
    assert published_article_ids(channel) == [1]


def test_republish_articles_publishes_nothing_when_stop_was_already_requested() -> None:
    channel = FakeChannel()
    stop_requested = RecordingStopEvent()
    stop_requested.set()

    republished = republish(
        channel=channel,
        articles=article_rows(2),
        delay_seconds=5,
        stop_requested=stop_requested,
    )

    assert republished == 0
    assert channel.publish_attempts == 0
    assert stop_requested.waits == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(UnroutableError([]), id="unroutable"),
        pytest.param(NackError([]), id="nacked-by-broker"),
        pytest.param(ChannelClosedByBroker(406, "PRECONDITION_FAILED"), id="channel-closed"),
    ],
)
def test_republish_articles_abandons_the_rest_when_a_publish_fails(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel(failing_publish=2, publish_error=error)

    with caplog.at_level(logging.ERROR):
        republished = republish(channel=channel, articles=article_rows(3))

    assert republished == 1
    assert channel.publish_attempts == 2
    assert published_article_ids(channel) == [1]
    assert "failed to republish article_id=2 to articles.fetched" in caplog.text


UNUSED_ENGINE = cast(Engine, object())


class PassDoubles:
    """Replaces the module's DB selection and broker connection with recorders."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        articles: list[ListUntransformedArticlesRow],
        connection: FakeConnection | None,
    ) -> None:
        self.select_calls: list[dict[str, object]] = []

        def select(**arguments: object) -> list[ListUntransformedArticlesRow]:
            self.select_calls.append(arguments)
            return articles

        def open_connection(rabbitmq_url: str) -> FakeConnection:
            if connection is None:
                raise AssertionError("no articles to republish must not open a connection")
            return connection

        monkeypatch.setattr(retransform_module, "select_untransformed_articles", select)
        monkeypatch.setattr(retransform_module, "_open_connection", open_connection)


def run_pass(
    min_age_minutes: int = 60,
    delay_seconds: float = 0,
    max_messages_per_run: int = 10,
    stop_requested: threading.Event | None = None,
) -> None:
    run_retransform_pass(
        engine=UNUSED_ENGINE,
        rabbitmq_url="amqp://unused",
        min_age_minutes=min_age_minutes,
        delay_seconds=delay_seconds,
        max_messages_per_run=max_messages_per_run,
        stop_requested=stop_requested or RecordingStopEvent(),
    )


def test_run_retransform_pass_republishes_the_selected_articles_and_closes_the_connection(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel()
    connection = FakeConnection(channel)
    doubles = PassDoubles(
        monkeypatch=monkeypatch, articles=article_rows(2), connection=connection
    )

    with caplog.at_level(logging.INFO):
        run_pass(min_age_minutes=15, max_messages_per_run=7)

    assert doubles.select_calls == [
        {"engine": UNUSED_ENGINE, "min_age_minutes": 15, "limit": 7}
    ]
    assert published_article_ids(channel) == [1, 2]
    assert channel.confirm_calls == 1
    assert connection.close_calls == 1
    assert (
        "republished 2 of 2 untransformed article(s) to articles.fetched (limit 7)"
        in caplog.text
    )


def test_run_retransform_pass_with_nothing_to_republish_does_not_connect(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    PassDoubles(monkeypatch=monkeypatch, articles=[], connection=None)

    with caplog.at_level(logging.INFO):
        run_pass()

    assert (
        "republished 0 of 0 untransformed article(s) to articles.fetched"
        in caplog.text
    )


def test_run_retransform_pass_reports_and_closes_after_a_publish_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    channel = FakeChannel(failing_publish=2, publish_error=UnroutableError([]))
    connection = FakeConnection(channel)
    PassDoubles(monkeypatch=monkeypatch, articles=article_rows(3), connection=connection)

    with caplog.at_level(logging.INFO):
        run_pass()

    assert published_article_ids(channel) == [1]
    assert connection.close_calls == 1
    assert (
        "republished 1 of 3 untransformed article(s) to articles.fetched (limit 10)"
        in caplog.text
    )


def test_run_retransform_pass_keeps_the_connection_error_when_the_broker_dropped_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = FakeChannel(
        failing_publish=1, publish_error=AMQPConnectionError("connection lost")
    )
    connection = FakeConnection(channel)
    connection.is_open = False
    PassDoubles(monkeypatch=monkeypatch, articles=article_rows(2), connection=connection)

    with pytest.raises(AMQPConnectionError):
        run_pass()

    assert connection.close_calls == 0


def test_run_retransform_pass_propagates_a_database_error_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    PassDoubles(monkeypatch=monkeypatch, articles=[], connection=None)

    def failing_select(**arguments: object) -> list[ListUntransformedArticlesRow]:
        raise ConnectionError("database down")

    monkeypatch.setattr(
        retransform_module, "select_untransformed_articles", failing_select
    )

    with pytest.raises(ConnectionError):
        run_pass()


def test_select_untransformed_articles_returns_the_rows_and_releases_the_connection(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    article_id = insert_catalog_article(
        title_vi=None,
        summary_vi=None,
        content_vi=None,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )

    rows = select_untransformed_articles(engine=engine, min_age_minutes=60, limit=10)

    assert [row.id for row in rows] == [article_id]
    assert cast(QueuePool, engine.pool).checkedout() == 0
