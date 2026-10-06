import logging
from typing import Protocol

from smartnews_common.messages import ArticleCrawled, ArticleFetched
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.messaging.topology import ARTICLES_CRAWLED

from smartnews_crawler.extraction.registry import ExtractorRegistry
from smartnews_crawler.fetching.base import PageFetcher

logger = logging.getLogger(__name__)


class ContentRecorder(Protocol):
    def record(self, article_id: int, content: str, extractor: str) -> None: ...


class CrawlerHandler:
    def __init__(
        self, fetcher: PageFetcher, extractors: ExtractorRegistry, recorder: ContentRecorder
    ) -> None:
        self._fetcher = fetcher
        self._extractors = extractors
        self._recorder = recorder

    def __call__(self, message: ArticleFetched, context: DeliveryContext) -> None:
        html = self._fetcher.fetch(message.url)
        extractor = self._extractors.resolve(message.source)
        content = extractor.extract(html, message.url)
        extractor_name = self._extractors.name_for(message.source)
        self._recorder.record(message.article_id, content, extractor_name)
        context.publisher.publish(ARTICLES_CRAWLED, ArticleCrawled.from_fetched(message, content))
        logger.info("crawled %s using %s", message.url, extractor_name)
