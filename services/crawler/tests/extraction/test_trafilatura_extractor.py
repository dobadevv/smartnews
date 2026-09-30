import pytest
from smartnews_crawler.extraction.base import ExtractionError
from smartnews_crawler.extraction.trafilatura_extractor import TrafilaturaExtractor

ARTICLE_HTML = """
<html>
<head><title>Local Team Wins Championship</title></head>
<body>
<nav>Home | Sports | World</nav>
<article>
<h1>Local Team Wins Championship</h1>
<p>The city's football club secured its first championship title in over a decade
after a dramatic final match that went into extra time on Saturday evening.</p>
<p>Thousands of fans packed the stadium to watch the decisive goal, scored in the
final minutes of extra time by the team's captain, sealing a historic victory for
the club and its supporters.</p>
<p>The coach praised the team's resilience throughout the season, noting that the
squad overcame several injuries and a difficult start to the campaign to reach
this milestone achievement.</p>
</article>
<footer>Copyright 2026</footer>
</body>
</html>
"""

EMPTY_HTML = "<html><body><nav>Home | Sports | World</nav></body></html>"


def test_extract_returns_the_articles_main_text() -> None:
    content = TrafilaturaExtractor().extract(
        ARTICLE_HTML.encode("utf-8"), "https://example.com/article"
    )

    assert "championship" in content.lower()
    assert "Home | Sports | World" not in content


def test_extract_raises_when_the_page_has_no_extractable_content() -> None:
    with pytest.raises(ExtractionError, match="example.com"):
        TrafilaturaExtractor().extract(EMPTY_HTML.encode("utf-8"), "https://example.com/empty")
