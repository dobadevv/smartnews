import trafilatura

from smartnews_crawler.extraction.base import ExtractionError


class TrafilaturaExtractor:
    def extract(self, html: str, url: str) -> str:
        # fast + favor_precision: trafilatura's default fallback extraction
        # returns the entire body text (nav, footer, ...) rather than None
        # when it can't isolate a content block, so ExtractionError would
        # never fire on a genuinely content-free page without these.
        content = trafilatura.extract(html, url=url, fast=True, favor_precision=True)
        if not content:
            raise ExtractionError(f"trafilatura found no content at {url}")
        return content
