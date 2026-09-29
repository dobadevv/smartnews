import logging
from datetime import UTC, datetime

import pytest

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.models import Article
from smartnews.pipeline import (
    run_notify_pipeline,
    run_print_pipeline,
    stream_enabled_sources,
    stream_published_in_current_month,
    stream_translated,
    stream_unseen_capped_to_max_posts,
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


def test_stream_published_in_current_month_keeps_article_published_this_month() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 9, 1, tzinfo=UTC)
    )

    result = list(stream_published_in_current_month([article], now=now))

    assert result == [article]


def test_stream_published_in_current_month_drops_article_published_last_month() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    article = make_article(
        "https://example.com/a", published_at=datetime(2026, 8, 31, tzinfo=UTC)
    )

    result = list(stream_published_in_current_month([article], now=now))

    assert result == []


def test_stream_published_in_current_month_drops_article_from_the_same_month_last_year() -> (
    None
):
    now = datetime(2026, 1, 15, tzinfo=UTC)
    article = make_article(
        "https://example.com/a", published_at=datetime(2025, 1, 20, tzinfo=UTC)
    )

    result = list(stream_published_in_current_month([article], now=now))

    assert result == []


def test_stream_published_in_current_month_keeps_article_with_unknown_published_date() -> (
    None
):
    now = datetime(2026, 9, 15, tzinfo=UTC)
    article = make_article("https://example.com/a", published_at=None)

    result = list(stream_published_in_current_month([article], now=now))

    assert result == [article]


def test_stream_published_in_current_month_defaults_to_the_real_current_month() -> None:
    article = make_article(
        "https://example.com/a", published_at=datetime.now(UTC)
    )

    result = list(stream_published_in_current_month([article]))

    assert result == [article]


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


def test_stream_unseen_capped_to_max_posts_keeps_article_unseen_on_at_least_one_channel() -> (
    None
):
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]
    sources = [SourceConfig(name="example", url="https://a")]

    result = list(
        stream_unseen_capped_to_max_posts([article], seen_store, notifiers, sources)
    )

    assert result == [article]


def test_stream_unseen_capped_to_max_posts_drops_article_seen_on_every_channel() -> None:
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    seen_store.mark_seen(article_key(article), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]
    sources = [SourceConfig(name="example", url="https://a")]

    result = list(
        stream_unseen_capped_to_max_posts([article], seen_store, notifiers, sources)
    )

    assert result == []


def test_stream_unseen_capped_to_max_posts_preserves_order_without_duplicates() -> None:
    articles = [
        make_article("https://example.com/0"),
        make_article("https://example.com/1"),
        make_article("https://example.com/2"),
    ]
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(articles[1]), "discord")
    seen_store.mark_seen(article_key(articles[1]), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]
    sources = [SourceConfig(name="example", url="https://a")]

    result = list(
        stream_unseen_capped_to_max_posts(articles, seen_store, notifiers, sources)
    )

    assert result == [articles[0], articles[2]]


def test_stream_unseen_capped_to_max_posts_returns_all_articles_when_no_notifiers() -> (
    None
):
    articles = [make_article("https://example.com/a")]
    seen_store = FakeSeenStore()
    sources = [SourceConfig(name="example", url="https://a")]

    result = list(stream_unseen_capped_to_max_posts(articles, seen_store, [], sources))

    assert result == articles


def test_dedup_before_cap_still_surfaces_an_older_unsent_article_once_the_newest_is_seen() -> (
    None
):
    """max_posts is a backlog-draining floor, applied after the dedup check:
    once a source's newest item has been sent, the next-oldest still-unsent
    item from that source surfaces instead of the source going silent for
    the rest of the cycle."""

    class ThreeArticlesFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            return [
                make_article(
                    f"https://example.com/{source.name}-{i}", source=source.name
                )
                for i in range(3)
            ]

    sources = [SourceConfig(name="hacker-news", url="https://a", max_posts=1)]
    fetched = stream_enabled_sources(sources, ThreeArticlesFetcher())
    seen_store = FakeSeenStore()
    notifier = FakeNotifier("discord")
    newest_article = make_article(
        "https://example.com/hacker-news-0", source="hacker-news"
    )
    seen_store.mark_seen(article_key(newest_article), "discord")

    result = stream_unseen_capped_to_max_posts(
        fetched, seen_store, [notifier], sources
    )

    assert [a.url for a in result] == ["https://example.com/hacker-news-1"]


def test_stream_unseen_capped_to_max_posts_caps_articles_per_source() -> None:
    articles = [
        make_article(f"https://example.com/{i}", source="hacker-news")
        for i in range(3)
    ]
    sources = [SourceConfig(name="hacker-news", url="https://a", max_posts=2)]
    seen_store = FakeSeenStore()
    notifier = FakeNotifier("discord")

    result = list(
        stream_unseen_capped_to_max_posts(iter(articles), seen_store, [notifier], sources)
    )

    assert result == articles[:2]


def test_stream_unseen_capped_to_max_posts_leaves_source_unbounded_when_no_max_configured() -> (
    None
):
    articles = [
        make_article(f"https://example.com/{i}", source="hacker-news")
        for i in range(3)
    ]
    sources = [SourceConfig(name="hacker-news", url="https://a")]
    seen_store = FakeSeenStore()
    notifier = FakeNotifier("discord")

    result = list(
        stream_unseen_capped_to_max_posts(iter(articles), seen_store, [notifier], sources)
    )

    assert result == articles


def test_stream_unseen_capped_to_max_posts_applies_independently_per_source() -> None:
    articles = [
        make_article("https://example.com/a0", source="source-a"),
        make_article("https://example.com/a1", source="source-a"),
        make_article("https://example.com/b0", source="source-b"),
        make_article("https://example.com/b1", source="source-b"),
    ]
    sources = [
        SourceConfig(name="source-a", url="https://a", max_posts=1),
        SourceConfig(name="source-b", url="https://b", max_posts=2),
    ]
    seen_store = FakeSeenStore()
    notifier = FakeNotifier("discord")

    result = list(
        stream_unseen_capped_to_max_posts(iter(articles), seen_store, [notifier], sources)
    )

    assert result == [articles[0], articles[2], articles[3]]


def test_stream_unseen_capped_to_max_posts_stops_checking_seen_status_once_cap_reached() -> (
    None
):
    """Regression test: once a source's cap is filled, further articles from
    that source must be skipped without a seen-store lookup, since they will
    be dropped by the cap regardless of their seen status. Checking anyway
    would waste one is_seen round-trip per leftover article on every cycle."""

    class CountingSeenStore(FakeSeenStore):
        def __init__(self) -> None:
            super().__init__()
            self.is_seen_call_count = 0

        def is_seen(self, key: str, channel: str) -> bool:
            self.is_seen_call_count += 1
            return super().is_seen(key, channel)

    articles = [
        make_article(f"https://example.com/{i}", source="hacker-news")
        for i in range(3)
    ]
    sources = [SourceConfig(name="hacker-news", url="https://a", max_posts=1)]
    seen_store = CountingSeenStore()
    notifier = FakeNotifier("discord")

    result = list(
        stream_unseen_capped_to_max_posts(iter(articles), seen_store, [notifier], sources)
    )

    assert result == [articles[0]]
    assert seen_store.is_seen_call_count == 1


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


def test_run_notify_pipeline_keeps_processing_later_articles_after_one_send_fails() -> (
    None
):
    articles = [
        make_article("https://example.com/0"),
        make_article("https://example.com/1"),
        make_article("https://example.com/2"),
    ]
    notifier = FakeNotifier(
        "discord", fail_urls=frozenset({"https://example.com/1"})
    )
    seen_store = FakeSeenStore()

    run_notify_pipeline(iter(articles), [notifier], seen_store)

    assert notifier.sent == [articles[0], articles[2]]
    assert seen_store.is_seen(article_key(articles[0]), "discord") is True
    assert seen_store.is_seen(article_key(articles[1]), "discord") is False
    assert seen_store.is_seen(article_key(articles[2]), "discord") is True


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


class FakeFilter:
    def __init__(self, *, fail_titles: frozenset[str] = frozenset()) -> None:
        self._fail_titles = fail_titles
        self.calls: list[str] = []

    def filter(self, article: Article) -> Article:
        self.calls.append(article.title)
        if article.title in self._fail_titles:
            return article
        return Article(
            title=f"translated: {article.title}",
            url=article.url,
            source=article.source,
            published_at=article.published_at,
            summary=article.summary,
        )


def test_stream_translated_applies_filter_to_each_article() -> None:
    articles = [
        make_article("https://example.com/0", title="a"),
        make_article("https://example.com/1", title="b"),
    ]
    article_filter = FakeFilter()

    result = list(stream_translated(iter(articles), article_filter))

    assert [a.title for a in result] == ["translated: a", "translated: b"]


def test_stream_translated_calls_filter_independently_per_article() -> None:
    articles = [
        make_article("https://example.com/0", title="fails"),
        make_article("https://example.com/1", title="succeeds"),
    ]
    article_filter = FakeFilter(fail_titles=frozenset({"fails"}))

    result = list(stream_translated(iter(articles), article_filter))

    assert result[0].title == "fails"
    assert result[1].title == "translated: succeeds"


def test_run_print_pipeline_prints_every_article(
    capsys: pytest.CaptureFixture[str],
) -> None:
    articles = [
        make_article("https://example.com/0", title="a"),
        make_article("https://example.com/1", title="b"),
    ]

    run_print_pipeline(iter(articles))

    out = capsys.readouterr().out
    assert "a" in out
    assert "b" in out


def test_pipeline_processes_each_article_end_to_end_before_the_next_is_fetched() -> (
    None
):
    events: list[str] = []

    class EventFetcher:
        def fetch(self, source: SourceConfig) -> list[Article]:
            events.append(f"fetch:{source.name}")
            return [
                make_article(f"https://example.com/{source.name}", source=source.name)
            ]

    class EventFilter:
        def filter(self, article: Article) -> Article:
            events.append(f"translate:{article.source}")
            return article

    class EventNotifier:
        channel = "discord"

        def send(self, article: Article) -> None:
            events.append(f"send:{article.source}")

    sources = [
        SourceConfig(name="s1", url="https://a.example.com/feed", enabled=True),
        SourceConfig(name="s2", url="https://b.example.com/feed", enabled=True),
    ]
    seen_store = FakeSeenStore()
    notifiers = [EventNotifier()]

    fetched = stream_enabled_sources(sources, EventFetcher())
    unseen = stream_unseen_capped_to_max_posts(fetched, seen_store, notifiers, sources)
    translated = stream_translated(unseen, EventFilter())
    run_notify_pipeline(translated, notifiers, seen_store)

    assert events == [
        "fetch:s1",
        "translate:s1",
        "send:s1",
        "fetch:s2",
        "translate:s2",
        "send:s2",
    ]
