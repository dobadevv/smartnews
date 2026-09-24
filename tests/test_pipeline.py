from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.models import Article
from smartnews.pipeline import fetch_enabled_sources, filter_unseen_articles


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


class FakeSeenStore:
    def __init__(self) -> None:
        self.seen: set[tuple[str, str]] = set()

    def filter_unseen(self, keys: list[str], channel: str) -> set[str]:
        return {key for key in keys if (key, channel) not in self.seen}

    def mark_seen(self, key: str, channel: str) -> None:
        self.seen.add((key, channel))


def make_article(url: str, title: str = "title") -> Article:
    return Article(
        title=title, url=url, source="example", published_at=None, summary=None
    )


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
