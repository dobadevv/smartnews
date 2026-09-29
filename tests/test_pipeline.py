import logging

import pytest

from smartnews.config import SourceConfig
from smartnews.models import Article
from smartnews.pipeline import stream_enabled_sources


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


def make_article(url: str, title: str = "title", source: str = "example") -> Article:
    return Article(title=title, url=url, source=source, published_at=None, summary=None)


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


def test_stream_enabled_sources_caps_articles_per_source_minimum_posts() -> None:
    class ManyArticlesFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            return [
                make_article(f"https://example.com/{i}", source=source.name)
                for i in range(3)
            ]

    sources = [
        SourceConfig(name="hacker-news", url="https://a", minimum_posts=2),
    ]

    articles = list(stream_enabled_sources(sources, ManyArticlesFetcher()))

    assert len(articles) == 2


def test_stream_enabled_sources_leaves_source_unbounded_when_no_minimum_configured() -> (
    None
):
    class ManyArticlesFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            return [
                make_article(f"https://example.com/{i}", source=source.name)
                for i in range(3)
            ]

    sources = [SourceConfig(name="hacker-news", url="https://a")]

    articles = list(stream_enabled_sources(sources, ManyArticlesFetcher()))

    assert len(articles) == 3


def test_stream_enabled_sources_applies_minimum_posts_independently_per_source() -> (
    None
):
    class ManyArticlesFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            count = 2 if source.name == "source-a" else 3
            return [
                make_article(f"https://example.com/{source.name}-{i}", source=source.name)
                for i in range(count)
            ]

    sources = [
        SourceConfig(name="source-a", url="https://a", minimum_posts=1),
        SourceConfig(name="source-b", url="https://b", minimum_posts=2),
    ]

    articles = list(stream_enabled_sources(sources, ManyArticlesFetcher()))

    assert [a.source for a in articles] == ["source-a", "source-b", "source-b"]


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
