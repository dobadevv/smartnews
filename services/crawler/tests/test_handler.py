import pytest
from pydantic import BaseModel
from smartnews_common.messages import ArticleCrawled, ArticleFetched
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.messaging.topology import ARTICLES_CRAWLED
from smartnews_common.models import Article
from smartnews_crawler.config import ContentSelectorOverride, CrawlerConfig
from smartnews_crawler.extraction.base import ExtractionError
from smartnews_crawler.extraction.registry import ExtractorRegistry
from smartnews_crawler.fetching.base import FetchError
from smartnews_crawler.handler import CrawlerHandler


class FakeFetcher:
    def __init__(self, html: bytes | None = None, error: Exception | None = None) -> None:
        self._html = html
        self._error = error

    def fetch(self, url: str) -> bytes:
        if self._error is not None:
            raise self._error
        assert self._html is not None
        return self._html


class RecordingRecorder:
    def __init__(self) -> None:
        self.recorded: list[tuple[int, str, str]] = []

    def record(self, article_id: int, content: str, extractor: str) -> None:
        self.recorded.append((article_id, content, extractor))


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, BaseModel]] = []

    def publish(self, routing_key: str, message: BaseModel) -> None:
        self.published.append((routing_key, message))


def make_fetched(source: str = "example-blog") -> ArticleFetched:
    article = Article(
        title="Hello", url="https://example.com/a", source=source, published_at=None, summary="S"
    )
    return ArticleFetched.from_article(article, article_id=5)


def make_handler(registry: ExtractorRegistry, fetcher: FakeFetcher, recorder: RecordingRecorder) -> CrawlerHandler:
    return CrawlerHandler(fetcher=fetcher, extractors=registry, recorder=recorder)


def test_handler_records_and_publishes_the_extracted_content() -> None:
    registry = ExtractorRegistry(
        CrawlerConfig(overrides={"example-blog": ContentSelectorOverride(content_selector="p")})
    )
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = make_handler(registry, FakeFetcher(html=b"<html><p>Body text</p></html>"), recorder)

    handler(make_fetched(), DeliveryContext(attempt=1, is_final_attempt=False, publisher=publisher))

    assert recorder.recorded == [(5, "Body text", "selector:example-blog")]
    assert publisher.published == [
        (ARTICLES_CRAWLED, ArticleCrawled.from_fetched(make_fetched(), "Body text"))
    ]


def test_handler_propagates_a_fetch_error_without_recording_or_publishing() -> None:
    registry = ExtractorRegistry(CrawlerConfig())
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = make_handler(registry, FakeFetcher(error=FetchError("blocked")), recorder)

    with pytest.raises(FetchError):
        handler(make_fetched(), DeliveryContext(attempt=1, is_final_attempt=False, publisher=publisher))

    assert (recorder.recorded, publisher.published) == ([], [])


def test_handler_propagates_an_extraction_error_without_recording_or_publishing() -> None:
    registry = ExtractorRegistry(
        CrawlerConfig(overrides={"example-blog": ContentSelectorOverride(content_selector="div.missing")})
    )
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = make_handler(registry, FakeFetcher(html=b"<html><p>no match</p></html>"), recorder)

    with pytest.raises(ExtractionError):
        handler(make_fetched(), DeliveryContext(attempt=1, is_final_attempt=False, publisher=publisher))

    assert (recorder.recorded, publisher.published) == ([], [])


def test_handler_propagates_even_on_the_final_attempt() -> None:
    """No degrade-forward fallback: unlike transformation, a failed crawl always
    goes through the retry ladder/DLQ, even when it is the last attempt."""
    registry = ExtractorRegistry(CrawlerConfig())
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = make_handler(registry, FakeFetcher(error=FetchError("still blocked")), recorder)

    with pytest.raises(FetchError):
        handler(make_fetched(), DeliveryContext(attempt=4, is_final_attempt=True, publisher=publisher))

    assert (recorder.recorded, publisher.published) == ([], [])
