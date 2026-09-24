from smartnews.config import SourceConfig
from smartnews.fetching.base import Fetcher
from smartnews.models import Article


def fetch_enabled_sources(
    sources: list[SourceConfig], fetcher: Fetcher
) -> list[Article]:
    articles: list[Article] = []
    for source in sources:
        if source.enabled:
            articles.extend(fetcher.fetch(source))
    return articles
