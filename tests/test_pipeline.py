import logging

import pytest

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.models import Article
from smartnews.pipeline import (
    run_notify_pipeline,
    stream_enabled_sources,
    stream_unseen_for_any_channel,
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


class FakeSeenStore:
    def __init__(self) -> None:
        self.seen: set[tuple[str, str]] = set()

    def is_seen(self, key: str, channel: str) -> bool:
        return (key, channel) in self.seen

    def mark_seen(self, key: str, channel: str) -> None:
        self.seen.add((key, channel))


class FakeNotifier:
    def __init__(
        self, channel: str, *, fail_urls: frozenset[str] = frozenset()
    ) -> None:
        self.channel = channel
        self.sent: list[Article] = []
        self._fail_urls = fail_urls

    def send(self, article: Article) -> None:
        if article.url in self._fail_urls:
            raise RuntimeError("boom")
        self.sent.append(article)


def test_stream_unseen_for_any_channel_keeps_article_unseen_on_at_least_one_channel() -> (
    None
):
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = list(stream_unseen_for_any_channel([article], seen_store, notifiers))

    assert result == [article]


def test_stream_unseen_for_any_channel_drops_article_seen_on_every_channel() -> None:
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    seen_store.mark_seen(article_key(article), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = list(stream_unseen_for_any_channel([article], seen_store, notifiers))

    assert result == []


def test_stream_unseen_for_any_channel_preserves_order_without_duplicates() -> None:
    articles = [
        make_article("https://example.com/0"),
        make_article("https://example.com/1"),
        make_article("https://example.com/2"),
    ]
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(articles[1]), "discord")
    seen_store.mark_seen(article_key(articles[1]), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = list(stream_unseen_for_any_channel(articles, seen_store, notifiers))

    assert result == [articles[0], articles[2]]


def test_stream_unseen_for_any_channel_returns_all_articles_when_no_notifiers() -> None:
    articles = [make_article("https://example.com/a")]
    seen_store = FakeSeenStore()

    result = list(stream_unseen_for_any_channel(articles, seen_store, []))

    assert result == articles


def test_run_notify_pipeline_sends_unseen_article_and_marks_it_seen() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()

    run_notify_pipeline(iter([article]), [notifier], seen_store)

    assert notifier.sent == [article]
    assert seen_store.is_seen(article_key(article), "discord") is True


def test_run_notify_pipeline_skips_send_when_already_seen() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")

    run_notify_pipeline(iter([article]), [notifier], seen_store)

    assert notifier.sent == []


def test_run_notify_pipeline_does_not_mark_seen_when_send_fails() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    seen_store = FakeSeenStore()

    run_notify_pipeline(iter([article]), [notifier], seen_store)

    assert notifier.sent == []
    assert seen_store.is_seen(article_key(article), "discord") is False


def test_run_notify_pipeline_still_dispatches_to_other_notifiers_when_one_fails() -> (
    None
):
    article = make_article("https://example.com/a")
    discord = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    telegram = FakeNotifier("telegram")
    seen_store = FakeSeenStore()

    run_notify_pipeline(iter([article]), [discord, telegram], seen_store)

    assert discord.sent == []
    assert telegram.sent == [article]
    assert seen_store.is_seen(article_key(article), "telegram") is True


def test_run_notify_pipeline_handles_each_notifier_independently_when_already_seen() -> (
    None
):
    article = make_article("https://example.com/a")
    discord = FakeNotifier("discord")
    telegram = FakeNotifier("telegram")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")

    run_notify_pipeline(iter([article]), [discord, telegram], seen_store)

    assert discord.sent == []
    assert telegram.sent == [article]


def test_run_notify_pipeline_logs_error_when_send_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    seen_store = FakeSeenStore()

    with caplog.at_level(logging.ERROR):
        run_notify_pipeline(iter([article]), [notifier], seen_store)

    messages = [record.getMessage() for record in caplog.records]
    assert any("discord" in message and article.url in message for message in messages)


def test_run_notify_pipeline_logs_sent_count_per_notifier(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()

    with caplog.at_level(logging.INFO):
        run_notify_pipeline(iter([article]), [notifier], seen_store)

    messages = [record.getMessage() for record in caplog.records]
    assert any("discord" in message and "1" in message for message in messages)
