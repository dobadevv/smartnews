from datetime import UTC, datetime

import pytest
from smartnews_common.models import Article
from smartnews_fetcher.config import SourceConfig
from smartnews_fetcher.rss import RssFetcher

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


SAMPLE_FEED_WITH_LINKLESS_ENTRY = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Example Blog</title>
<item>
<title>No link here</title>
<description>Entry without a link</description>
</item>
<item>
<title>Hello World</title>
<link>https://example.com/hello-world</link>
</item>
</channel>
</rss>
"""


def test_fetch_skips_entries_without_a_link() -> None:
    source = SourceConfig(name="example-blog", url=SAMPLE_FEED_WITH_LINKLESS_ENTRY)

    articles = RssFetcher().fetch(source)

    assert [article.url for article in articles] == ["https://example.com/hello-world"]


def test_fetch_stamps_the_source_category_on_every_article() -> None:
    source = SourceConfig(name="example-blog", url=SAMPLE_FEED, category="architecture")

    articles = RssFetcher().fetch(source)

    assert [article.category for article in articles] == ["architecture"]


SAMPLE_ATOM_FEED_WITH_ONLY_UPDATED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Releases</title>
<entry>
<title>v1.2.3</title>
<link rel="alternate" href="https://example.com/releases/v1.2.3"/>
<updated>2026-10-10T05:28:41Z</updated>
</entry>
</feed>
"""


def test_fetch_falls_back_to_the_updated_date_when_published_is_missing() -> None:
    source = SourceConfig(
        name="example-releases", url=SAMPLE_ATOM_FEED_WITH_ONLY_UPDATED
    )

    articles = RssFetcher().fetch(source)

    assert articles[0].published_at == datetime(2026, 10, 10, 5, 28, 41, tzinfo=UTC)


def feed_with_pub_date(pub_date: str) -> str:
    return f"""<?xml version="1.0"?>
<rss version="2.0">
<channel>
<title>Example News</title>
<item>
<title>Hello World</title>
<link>https://example.com/hello-world</link>
<pubDate>{pub_date}</pubDate>
</item>
</channel>
</rss>
"""


@pytest.mark.parametrize(
    ("pub_date", "timezone", "expected"),
    [
        pytest.param(
            "10/8/2026 2:06:00 PM",
            "Asia/Ho_Chi_Minh",
            datetime(2026, 10, 8, 7, 6, tzinfo=UTC),
            id="month-first 12-hour date in the source timezone",
        ),
        pytest.param(
            "9/29/2026 7:30:00 AM",
            "UTC",
            datetime(2026, 9, 29, 7, 30, tzinfo=UTC),
            id="month-first 12-hour date with a plain space defaults to UTC",
        ),
        pytest.param("not a date", "UTC", None, id="unrecognised date stays unknown"),
    ],
)
def test_fetch_parses_month_first_dates_without_an_offset(
    pub_date: str, timezone: str, expected: datetime | None
) -> None:
    source = SourceConfig(
        name="example-news", url=feed_with_pub_date(pub_date), timezone=timezone
    )

    articles = RssFetcher().fetch(source)

    assert articles[0].published_at == expected
