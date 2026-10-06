import pytest
from pydantic import BaseModel
from smartnews_common.dedup import article_key
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.topology import ARTICLES_FETCHED
from smartnews_common.models import Article
from smartnews_fetcher.publishing import TransactionalArticlePublisher
from sqlalchemy import Engine, text


class RecordingPublisher:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.published: list[tuple[str, BaseModel]] = []
        self._error = error

    def publish(self, routing_key: str, message: BaseModel) -> None:
        if self._error is not None:
            raise self._error
        self.published.append((routing_key, message))


def make_article() -> Article:
    return Article(
        title="Title", url="https://example.com/a", source="s", published_at=None, summary=None
    )


def make_publisher(engine: Engine, publisher: RecordingPublisher) -> TransactionalArticlePublisher:
    return TransactionalArticlePublisher(engine=engine, publisher=publisher)


def stored_article_count(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM articles")).scalar_one()


def test_publish_if_new_stores_and_publishes_an_unseen_article(engine: Engine) -> None:
    publisher = RecordingPublisher()
    article = make_article()

    is_new = make_publisher(engine, publisher).publish_if_new(article)

    assert is_new is True
    [(routing_key, message)] = publisher.published
    assert routing_key == ARTICLES_FETCHED
    assert isinstance(message, ArticleFetched)
    assert message.hash_url == article_key(article)
    assert message.to_article() == article
    assert stored_article_count(engine) == 1


def test_publish_if_new_skips_an_article_that_is_already_stored(engine: Engine) -> None:
    publisher = RecordingPublisher()
    new_article_publisher = make_publisher(engine, publisher)
    new_article_publisher.publish_if_new(make_article())

    is_new = new_article_publisher.publish_if_new(make_article())

    assert is_new is False
    assert len(publisher.published) == 1


def test_publish_failure_rolls_back_so_the_article_stays_new(engine: Engine) -> None:
    failing = make_publisher(engine, RecordingPublisher(error=ConnectionError("broker down")))

    with pytest.raises(ConnectionError):
        failing.publish_if_new(make_article())

    assert stored_article_count(engine) == 0
    assert make_publisher(engine, RecordingPublisher()).publish_if_new(make_article()) is True
