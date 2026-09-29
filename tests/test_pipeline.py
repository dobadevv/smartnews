import logging

import pytest

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.models import Article
from smartnews.pipeline import (
    dispatch_to_notifiers,
    fetch_enabled_sources,
    filter_unseen_articles,
    limit_to_minimum_posts,
    select_unseen_for_any_channel,
)


class FakeFetcher:
    def __init__(self) -> None:
        self.fetched_sources: list[SourceConfig] = []

    def fetch(self, source: SourceConfig) -> list[Article]:
        self.fetched_sources.append(source)
        return [
            Article(
                title=f"article from {source.name}",
                url=f"https://example.com/{source.name}",
                source=source.name,
                published_at=None,
                summary=None,
            )
        ]


def test_fetch_enabled_sources_skips_disabled_sources() -> None:
    sources = [
        SourceConfig(
            name="enabled-source", url="https://a.example.com/feed", enabled=True
        ),
        SourceConfig(
            name="disabled-source", url="https://b.example.com/feed", enabled=False
        ),
    ]
    fetcher = FakeFetcher()

    articles = fetch_enabled_sources(sources, fetcher)

    assert [a.source for a in articles] == ["enabled-source"]
    assert [s.name for s in fetcher.fetched_sources] == ["enabled-source"]


def test_fetch_enabled_sources_aggregates_articles_from_all_enabled_sources() -> None:
    sources = [
        SourceConfig(name="first", url="https://a.example.com/feed", enabled=True),
        SourceConfig(name="second", url="https://b.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher()

    articles = fetch_enabled_sources(sources, fetcher)

    assert [a.source for a in articles] == ["first", "second"]


def test_fetch_enabled_sources_logs_progress_per_source_and_total(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sources = [
        SourceConfig(name="first", url="https://a.example.com/feed", enabled=True),
        SourceConfig(name="second", url="https://b.example.com/feed", enabled=True),
    ]
    fetcher = FakeFetcher()

    with caplog.at_level(logging.INFO):
        fetch_enabled_sources(sources, fetcher)

    messages = [record.getMessage() for record in caplog.records]
    assert any("first" in message for message in messages)
    assert any("second" in message for message in messages)
    assert any("2" in message for message in messages)


class FakeSeenStore:
    def __init__(self) -> None:
        self.seen: set[tuple[str, str]] = set()

    def filter_unseen(self, keys: list[str], channel: str) -> set[str]:
        return {key for key in keys if (key, channel) not in self.seen}

    def mark_seen(self, key: str, channel: str) -> None:
        self.seen.add((key, channel))


def make_article(url: str, title: str = "title", source: str = "example") -> Article:
    return Article(title=title, url=url, source=source, published_at=None, summary=None)


def test_filter_unseen_articles_keeps_articles_not_yet_seen_on_channel() -> None:
    articles = [
        make_article("https://example.com/a"),
        make_article("https://example.com/b"),
    ]
    seen_store = FakeSeenStore()

    unseen = filter_unseen_articles(articles, seen_store, channel="discord")

    assert unseen == articles


def test_filter_unseen_articles_drops_articles_already_seen_on_channel() -> None:
    seen_article = make_article("https://example.com/a")
    unseen_article = make_article("https://example.com/b")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(seen_article), channel="discord")

    unseen = filter_unseen_articles(
        [seen_article, unseen_article], seen_store, channel="discord"
    )

    assert unseen == [unseen_article]


def test_filter_unseen_articles_is_scoped_per_channel() -> None:
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), channel="discord")

    unseen_on_telegram = filter_unseen_articles(
        [article], seen_store, channel="telegram"
    )

    assert unseen_on_telegram == [article]


class FakeNotifier:
    def __init__(
        self, channel: str, *, fail_urls: frozenset[str] = frozenset()
    ) -> None:
        self.channel = channel
        self.sent: list[Article] = []
        self._fail_urls = fail_urls

    def send(self, articles: list[Article]) -> None:
        for article in articles:
            if article.url in self._fail_urls:
                raise RuntimeError("boom")
            self.sent.append(article)


def test_dispatch_to_notifiers_sends_unseen_articles_and_marks_them_seen() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()

    dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    assert notifier.sent == [article]
    assert seen_store.filter_unseen([article_key(article)], "discord") == set()


def test_dispatch_to_notifiers_skips_send_when_nothing_unseen() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")

    dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    assert notifier.sent == []


def test_dispatch_to_notifiers_logs_how_many_were_sent_per_channel(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()

    with caplog.at_level(logging.INFO):
        dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    messages = [record.getMessage() for record in caplog.records]
    assert any("discord" in message and "1" in message for message in messages)


def test_dispatch_to_notifiers_logs_when_nothing_to_send(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")

    with caplog.at_level(logging.INFO):
        dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    messages = [record.getMessage() for record in caplog.records]
    assert any("discord" in message for message in messages)


def test_dispatch_to_notifiers_does_not_mark_seen_when_send_fails() -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    seen_store = FakeSeenStore()

    dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    assert notifier.sent == []
    assert seen_store.filter_unseen([article_key(article)], "discord") == {
        article_key(article)
    }


def test_dispatch_to_notifiers_marks_earlier_successes_seen_when_a_later_send_fails() -> (
    None
):
    articles = [
        make_article("https://example.com/0"),
        make_article("https://example.com/1"),
        make_article("https://example.com/2"),
    ]
    notifier = FakeNotifier("discord", fail_urls=frozenset({"https://example.com/1"}))
    seen_store = FakeSeenStore()

    dispatch_to_notifiers(articles, [notifier], seen_store, sources=[])

    assert notifier.sent == [articles[0], articles[2]]
    assert seen_store.filter_unseen(
        [article_key(article) for article in articles], "discord"
    ) == {article_key(articles[1])}


def test_dispatch_to_notifiers_still_dispatches_to_other_notifiers_when_one_fails() -> (
    None
):
    article = make_article("https://example.com/a")
    discord = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    telegram = FakeNotifier("telegram")
    seen_store = FakeSeenStore()

    dispatch_to_notifiers([article], [discord, telegram], seen_store, sources=[])

    assert discord.sent == []
    assert telegram.sent == [article]
    assert seen_store.filter_unseen([article_key(article)], "telegram") == set()


def test_dispatch_to_notifiers_logs_error_when_send_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    article = make_article("https://example.com/a")
    notifier = FakeNotifier("discord", fail_urls=frozenset({article.url}))
    seen_store = FakeSeenStore()

    with caplog.at_level(logging.ERROR):
        dispatch_to_notifiers([article], [notifier], seen_store, sources=[])

    messages = [record.getMessage() for record in caplog.records]
    assert any("discord" in message and article.url in message for message in messages)


def test_dispatch_to_notifiers_limits_articles_to_sources_minimum_posts() -> None:
    articles = [
        make_article("https://example.com/0", source="hacker-news"),
        make_article("https://example.com/1", source="hacker-news"),
        make_article("https://example.com/2", source="hacker-news"),
    ]
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()
    sources = [SourceConfig(name="hacker-news", url="https://a", minimum_posts=2)]

    dispatch_to_notifiers(articles, [notifier], seen_store, sources=sources)

    assert notifier.sent == articles[:2]
    assert seen_store.filter_unseen(
        [article_key(article) for article in articles], "discord"
    ) == {article_key(articles[2])}


def test_dispatch_to_notifiers_sends_all_unseen_when_source_has_no_minimum_posts() -> (
    None
):
    articles = [
        make_article("https://example.com/0", source="hacker-news"),
        make_article("https://example.com/1", source="hacker-news"),
    ]
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()

    dispatch_to_notifiers(articles, [notifier], seen_store, sources=[])

    assert notifier.sent == articles


def test_dispatch_to_notifiers_applies_minimum_posts_independently_per_source() -> None:
    articles = [
        make_article("https://example.com/a0", source="source-a"),
        make_article("https://example.com/a1", source="source-a"),
        make_article("https://example.com/b0", source="source-b"),
        make_article("https://example.com/b1", source="source-b"),
    ]
    notifier = FakeNotifier("discord")
    seen_store = FakeSeenStore()
    sources = [
        SourceConfig(name="source-a", url="https://a", minimum_posts=1),
        SourceConfig(name="source-b", url="https://b", minimum_posts=2),
    ]

    dispatch_to_notifiers(articles, [notifier], seen_store, sources=sources)

    assert notifier.sent == [articles[0], articles[2], articles[3]]


def test_dispatch_to_notifiers_handles_each_notifier_independently() -> None:
    article = make_article("https://example.com/a")
    discord = FakeNotifier("discord")
    telegram = FakeNotifier("telegram")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")

    dispatch_to_notifiers([article], [discord, telegram], seen_store, sources=[])

    assert discord.sent == []
    assert telegram.sent == [article]


def test_select_unseen_for_any_channel_keeps_article_unseen_on_at_least_one_channel() -> (
    None
):
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = select_unseen_for_any_channel([article], seen_store, notifiers)

    assert result == [article]


def test_select_unseen_for_any_channel_drops_article_seen_on_every_channel() -> None:
    article = make_article("https://example.com/a")
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(article), "discord")
    seen_store.mark_seen(article_key(article), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = select_unseen_for_any_channel([article], seen_store, notifiers)

    assert result == []


def test_select_unseen_for_any_channel_preserves_order_without_duplicates() -> None:
    articles = [
        make_article("https://example.com/0"),
        make_article("https://example.com/1"),
        make_article("https://example.com/2"),
    ]
    seen_store = FakeSeenStore()
    seen_store.mark_seen(article_key(articles[1]), "discord")
    seen_store.mark_seen(article_key(articles[1]), "telegram")
    notifiers = [FakeNotifier("discord"), FakeNotifier("telegram")]

    result = select_unseen_for_any_channel(articles, seen_store, notifiers)

    assert result == [articles[0], articles[2]]


def test_select_unseen_for_any_channel_returns_all_articles_when_no_notifiers() -> None:
    articles = [make_article("https://example.com/a")]
    seen_store = FakeSeenStore()

    result = select_unseen_for_any_channel(articles, seen_store, [])

    assert result == articles


def test_limit_to_minimum_posts_caps_articles_per_source() -> None:
    articles = [
        make_article("https://example.com/0", source="hacker-news"),
        make_article("https://example.com/1", source="hacker-news"),
        make_article("https://example.com/2", source="hacker-news"),
    ]
    sources = [SourceConfig(name="hacker-news", url="https://a", minimum_posts=2)]

    result = limit_to_minimum_posts(articles, sources)

    assert result == articles[:2]


def test_limit_to_minimum_posts_leaves_source_unbounded_when_no_minimum_configured() -> (
    None
):
    articles = [
        make_article("https://example.com/0", source="hacker-news"),
        make_article("https://example.com/1", source="hacker-news"),
    ]

    result = limit_to_minimum_posts(articles, sources=[])

    assert result == articles


def test_limit_to_minimum_posts_applies_independently_per_source() -> None:
    articles = [
        make_article("https://example.com/a0", source="source-a"),
        make_article("https://example.com/a1", source="source-a"),
        make_article("https://example.com/b0", source="source-b"),
        make_article("https://example.com/b1", source="source-b"),
    ]
    sources = [
        SourceConfig(name="source-a", url="https://a", minimum_posts=1),
        SourceConfig(name="source-b", url="https://b", minimum_posts=2),
    ]

    result = limit_to_minimum_posts(articles, sources)

    assert result == [articles[0], articles[2], articles[3]]
