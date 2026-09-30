import pytest
from smartnews_crawler.extraction.base import ExtractionError
from smartnews_crawler.extraction.selector_extractor import SelectorExtractor

HTML = """
<html><body>
<nav>Home</nav>
<div class="article-body"><p>The main story text goes here.</p></div>
</body></html>
"""


def test_extract_returns_the_text_within_the_selector() -> None:
    content = SelectorExtractor("div.article-body").extract(
        HTML.encode("utf-8"), "https://example.com/a"
    )

    assert content == "The main story text goes here."


def test_extract_raises_when_the_selector_matches_nothing() -> None:
    with pytest.raises(ExtractionError, match="div.missing"):
        SelectorExtractor("div.missing").extract(HTML.encode("utf-8"), "https://example.com/a")
