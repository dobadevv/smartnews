from bs4 import BeautifulSoup

from smartnews_crawler.extraction.base import ExtractionError


class SelectorExtractor:
    def __init__(self, css_selector: str) -> None:
        self._css_selector = css_selector

    def extract(self, html: str, url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        element = soup.select_one(self._css_selector)
        if element is None:
            raise ExtractionError(
                f"selector {self._css_selector!r} matched nothing at {url}"
            )
        text = element.get_text(separator="\n", strip=True)
        if not text:
            raise ExtractionError(
                f"selector {self._css_selector!r} matched empty content at {url}"
            )
        return text
