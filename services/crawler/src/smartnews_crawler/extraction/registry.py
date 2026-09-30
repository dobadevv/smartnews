from smartnews_crawler.config import CrawlerConfig
from smartnews_crawler.extraction.base import Extractor
from smartnews_crawler.extraction.selector_extractor import SelectorExtractor
from smartnews_crawler.extraction.trafilatura_extractor import TrafilaturaExtractor

DEFAULT_EXTRACTOR_NAME = "trafilatura"


class ExtractorRegistry:
    def __init__(self, config: CrawlerConfig) -> None:
        self._default = TrafilaturaExtractor()
        self._overrides: dict[str, SelectorExtractor] = {
            source: SelectorExtractor(override.content_selector)
            for source, override in config.overrides.items()
        }

    def resolve(self, source: str) -> Extractor:
        return self._overrides.get(source, self._default)

    def name_for(self, source: str) -> str:
        if source in self._overrides:
            return f"selector:{source}"
        return DEFAULT_EXTRACTOR_NAME
