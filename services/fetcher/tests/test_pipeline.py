import logging
from datetime import UTC, datetime

import pytest
from smartnews_common.models import Article
from smartnews_fetcher.config import SourceConfig
from smartnews_fetcher.pipeline import (
    stream_enabled_sources,
    stream_new_capped_to_max_posts,
    stream_published_within_lookback_days,
)


class FakeFetcher:
    def __init__(
        self, *, fail_sources: frozenset[str] = frozenset()
    ) -> None:
        self.fetched_sources: list[SourceConfig] = []
        self._fail_sources = fail_sources

    def fetch(self, source: SourceConfig) -> list[Article]:
        self.fetched_sources.append(source)
        if source.name in self._fail_sources:
            raise RuntimeError("boom")
        return [
            Article(
                title=f"article from {source.name}",
                url=f"https://example.com/{source.name}",
                source=source.name,
                published_at=None,
                summary=None,
            )
        ]


def make_article(
    url: str,
    title: str = "title",
    source: str = "example",
    published_at: datetime | None = None,
) -> Article:
    return Article(
        title=title, url=url, source=source, published_at=published_at, summary=None
    )


def test_stream_enabled_sources_skips_disabled_sources() -> None:
    sources = [
        SourceConfig(
            name="enabled-source", url="https://a.example.com/feed", enabled=True
        ),
        SourceConfig(
            name="disabled-source", url="https://b.example.com/feed", enabled=False
        ),
    ]
    fetcher = FakeFetcher()

    articles = list(stream_enabled_sources(sources, fetcher))

    assert [a.source for a in articles] == ["enabled-source"]
    assert [s.name for s in fetcher.fetched_sources] == ["enabled-source"]


def test_stream_enabled_sources_yields_articles_from_all_enabled_sources_in_order() -> (
    None
):
    sources = [
        SourceConfig(name="first", url="https://a.example.com/feed", enabled=True),
        SourceConfig(name="second", url="https://b.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher()

    articles = list(stream_enabled_sources(sources, fetcher))

    assert [a.source for a in articles] == ["first", "second"]


def test_stream_enabled_sources_logs_progress_per_source(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [
        SourceConfig(name="first", url="https://a.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher()

    with caplog.at_level(logging.INFO):
        list(stream_enabled_sources(sources, fetcher))

    messages = [record.getMessage() for record in caplog.records]
    assert any("first" in message for message in messages)


def test_stream_enabled_sources_yields_all_fetched_articles_without_capping() -> None:
    class ManyArticlesFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            return [
                make_article(f"https://example.com/{i}", source=source.name)
                for i in range(3)
            ]

    sources = [
        SourceConfig(name="hacker-news", url="https://a", max_posts=1),
    ]

    articles = list(stream_enabled_sources(sources, ManyArticlesFetcher()))

    assert len(articles) == 3


def test_stream_enabled_sources_skips_a_failing_source_and_continues_to_the_next() -> (
    None
):
    sources = [
        SourceConfig(name="broken", url="https://a.example.com/feed", enabled=True),
        SourceConfig(name="healthy", url="https://b.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher(fail_sources=frozenset({"broken"}))

    articles = list(stream_enabled_sources(sources, fetcher))

    assert [a.source for a in articles] == ["healthy"]
    assert [s.name for s in fetcher.fetched_sources] == ["broken", "healthy"]


def test_stream_enabled_sources_logs_the_fetch_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [
        SourceConfig(name="broken", url="https://a.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher(fail_sources=frozenset({"broken"}))

    with caplog.at_level(logging.ERROR):
        list(stream_enabled_sources(sources, fetcher))

    messages = [record.getMessage() for record in caplog.records]
    assert any("broken" in message for message in messages)


def test_stream_published_within_lookback_days_keeps_article_inside_the_window() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 9, 10, tzinfo=UTC)
    )

    result = list(stream_published_within_lookback_days([article], sources, now=now))

    assert result == [article]


def test_stream_published_within_lookback_days_drops_article_older_than_the_window() -> (
    None
):
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 9, 1, tzinfo=UTC)
    )

    result = list(stream_published_within_lookback_days([article], sources, now=now))

    assert result == []


def test_stream_published_within_lookback_days_keeps_article_exactly_at_the_boundary() -> (
    None
):
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 9, 8, tzinfo=UTC)
    )

    result = list(stream_published_within_lookback_days([article], sources, now=now))

    assert result == [article]


def test_stream_published_within_lookback_days_applies_independently_per_source() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [
        SourceConfig(name="strict", url="https://a", lookback_days=1),
        SourceConfig(name="lenient", url="https://b", lookback_days=7),
    ]
    published_three_days_ago = datetime(2026, 9, 12, tzinfo=UTC)
    strict_article = make_article(
        "https://example.com/strict",
        source="strict",
        published_at=published_three_days_ago,
    )
    lenient_article = make_article(
        "https://example.com/lenient",
        source="lenient",
        published_at=published_three_days_ago,
    )

    result = list(
        stream_published_within_lookback_days(
            [strict_article, lenient_article], sources, now=now
        )
    )

    assert result == [lenient_article]


def test_stream_published_within_lookback_days_keeps_article_with_unknown_published_date() -> (
    None
):
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article("https://example.com/a", published_at=None)

    result = list(stream_published_within_lookback_days([article], sources, now=now))

    assert result == [article]


def test_stream_published_within_lookback_days_keeps_future_dated_article() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 9, 20, tzinfo=UTC)
    )

    result = list(stream_published_within_lookback_days([article], sources, now=now))

    assert result == [article]


def test_stream_published_within_lookback_days_defaults_to_the_real_current_time() -> (
    None
):
    sources = [SourceConfig(name="example", url="https://a", lookback_days=7)]
    article = make_article(
        "https://example.com/a", published_at=datetime.now(UTC)
    )

    result = list(stream_published_within_lookback_days([article], sources))

    assert result == [article]


class FakeNewArticlePublisher:
    def __init__(self, already_seen_urls: frozenset[str] = frozenset()) -> None:
        self.checked: list[Article] = []
        self.published: list[Article] = []
        self._seen_urls = set(already_seen_urls)

    def publish_if_new(self, article: Article) -> bool:
        self.checked.append(article)
        if article.url in self._seen_urls:
            return False
        self._seen_urls.add(article.url)
        self.published.append(article)
        return True


def test_stream_new_capped_to_max_posts_publishes_and_yields_new_articles() -> None:
    articles = [make_article("https://e.com/a"), make_article("https://e.com/b")]
    publisher = FakeNewArticlePublisher()

    result = list(stream_new_capped_to_max_posts(iter(articles), [], publisher))

    assert result == articles
    assert publisher.published == articles


def test_stream_new_capped_to_max_posts_skips_already_seen_articles() -> None:
    publisher = FakeNewArticlePublisher(already_seen_urls=frozenset({"https://e.com/a"}))

    result = list(
        stream_new_capped_to_max_posts(
            iter([make_article("https://e.com/a"), make_article("https://e.com/b")]),
            [],
            publisher,
        )
    )

    assert [article.url for article in result] == ["https://e.com/b"]


def test_seen_article_does_not_use_up_the_cap_so_an_older_unsent_one_surfaces() -> None:
    sources = [SourceConfig(name="example", url="https://a", max_posts=1)]
    publisher = FakeNewArticlePublisher(already_seen_urls=frozenset({"https://e.com/newest"}))

    result = list(
        stream_new_capped_to_max_posts(
            iter([make_article("https://e.com/newest"), make_article("https://e.com/older")]),
            sources,
            publisher,
        )
    )

    assert [article.url for article in result] == ["https://e.com/older"]


@pytest.mark.parametrize(
    ("sources", "want_urls"),
    [
        pytest.param(
            [SourceConfig(name="example", url="https://a", max_posts=2)],
            ["https://e.com/1", "https://e.com/2"],
            id="capped",
        ),
        pytest.param(
            [SourceConfig(name="example", url="https://a")],
            ["https://e.com/1", "https://e.com/2", "https://e.com/3"],
            id="no max configured",
        ),
    ],
)
def test_stream_new_capped_to_max_posts_applies_the_source_cap(
    sources: list[SourceConfig], want_urls: list[str]
) -> None:
    articles = [make_article(f"https://e.com/{n}") for n in (1, 2, 3)]

    result = list(stream_new_capped_to_max_posts(iter(articles), sources, FakeNewArticlePublisher()))

    assert [article.url for article in result] == want_urls


def test_stream_new_capped_to_max_posts_caps_each_source_independently() -> None:
    sources = [
        SourceConfig(name="first", url="https://a", max_posts=1),
        SourceConfig(name="second", url="https://b", max_posts=1),
    ]
    articles = [
        make_article("https://e.com/f1", source="first"),
        make_article("https://e.com/f2", source="first"),
        make_article("https://e.com/s1", source="second"),
    ]

    result = list(stream_new_capped_to_max_posts(iter(articles), sources, FakeNewArticlePublisher()))

    assert [article.url for article in result] == ["https://e.com/f1", "https://e.com/s1"]


def test_stream_new_capped_to_max_posts_stops_touching_storage_once_the_cap_is_filled() -> None:
    sources = [SourceConfig(name="example", url="https://a", max_posts=1)]
    publisher = FakeNewArticlePublisher()

    list(
        stream_new_capped_to_max_posts(
            iter([make_article("https://e.com/1"), make_article("https://e.com/2")]),
            sources,
            publisher,
        )
    )

    assert [article.url for article in publisher.checked] == ["https://e.com/1"]


def test_same_url_in_two_sources_is_published_once_without_using_the_second_sources_cap() -> None:
    sources = [
        SourceConfig(name="hacker-news", url="https://a", max_posts=1),
        SourceConfig(name="lobsters", url="https://b", max_posts=1),
    ]
    articles = [
        make_article("https://e.com/shared", source="hacker-news"),
        make_article("https://e.com/shared", source="lobsters"),
        make_article("https://e.com/only-lobsters", source="lobsters"),
    ]

    result = list(stream_new_capped_to_max_posts(iter(articles), sources, FakeNewArticlePublisher()))

    assert [(article.source, article.url) for article in result] == [
        ("hacker-news", "https://e.com/shared"),
        ("lobsters", "https://e.com/only-lobsters"),
    ]
