from smartnews.config import SourceConfig
from smartnews.models import Article
from smartnews.pipeline import fetch_enabled_sources


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
