import pytest
from smartnews_common.messages import ArticleCrawled
from smartnews_common.messaging.topology import ARTICLES_CRAWLED
from smartnews_transformation.config import FilterConfig
from smartnews_transformation.content_consumer import build_content_consumer

RABBITMQ_URL = "amqp://guest:guest@localhost:5672/%2F"


class NullContentRecorder:
    def record_content(self, article_id: int, content: str) -> None:
        pass


def test_build_content_consumer_returns_none_when_the_filter_is_disabled() -> None:
    result = build_content_consumer(
        FilterConfig(enabled=False), RABBITMQ_URL, NullContentRecorder()
    )

    assert result is None


def test_build_content_consumer_consumes_crawled_articles_and_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    consumer = build_content_consumer(
        FilterConfig(enabled=True, provider="groq"), RABBITMQ_URL, NullContentRecorder()
    )

    deps = consumer._deps
    assert (deps.queue, deps.message_type, deps.output_queues) == (
        ARTICLES_CRAWLED, ArticleCrawled, ()
    )
