from datetime import UTC, datetime

from smartnews.config import SourceConfig
from smartnews.fetching.rss import RssFetcher
from smartnews.models import Article

SAMPLE_FEED = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Example Blog</title>
<item>
<title>Hello World</title>
<link>https://example.com/hello-world</link>
<description>An introductory post</description>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
</item>
</channel>
</rss>
"""


def test_fetch_returns_articles_parsed_from_feed_entries() -> None:
    source = SourceConfig(name="example-blog", url=SAMPLE_FEED)
    fetcher = RssFetcher()

    articles = fetcher.fetch(source)

    assert articles == [
        Article(
            title="Hello World",
            url="https://example.com/hello-world",
            source="example-blog",
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
            summary="An introductory post",
        )
    ]


SAMPLE_FEED_WITHOUT_PUB_DATE = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Example Blog</title>
<item>
<title>Hello World</title>
<link>https://example.com/hello-world</link>
<description>An introductory post</description>
</item>
</channel>
</rss>
"""


def test_fetch_leaves_published_at_none_when_feed_has_no_date() -> None:
    source = SourceConfig(name="example-blog", url=SAMPLE_FEED_WITHOUT_PUB_DATE)
    fetcher = RssFetcher()

    articles = fetcher.fetch(source)

    assert articles[0].published_at is None


SAMPLE_FEED_WITH_HTML_SUMMARY = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Example Blog</title>
<item>
<title>Hello World</title>
<link>https://example.com/hello-world</link>
<description><![CDATA[<p>Article URL: <a href="https://example.com/hello-world">https://example.com/hello-world</a></p><p>Points: 22</p>]]></description>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
</item>
</channel>
</rss>
"""


def test_fetch_strips_html_markup_from_summary() -> None:
    source = SourceConfig(name="example-blog", url=SAMPLE_FEED_WITH_HTML_SUMMARY)
    fetcher = RssFetcher()

    articles = fetcher.fetch(source)

    assert articles[0].summary == (
        "Article URL: https://example.com/hello-world Points: 22"
    )
