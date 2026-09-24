from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.fetching.base import Fetcher
from smartnews.models import Article
from smartnews.repository.base import SeenStore


def fetch_enabled_sources(
    sources: list[SourceConfig], fetcher: Fetcher
) -> list[Article]:
    articles: list[Article] = []
    for source in sources:
        if source.enabled:
            articles.extend(fetcher.fetch(source))
    return articles


def filter_unseen_articles(
    articles: list[Article], seen_store: SeenStore, channel: str
) -> list[Article]:
    keys = [article_key(article) for article in articles]
    unseen_keys = seen_store.filter_unseen(keys, channel)
    return [article for article, key in zip(articles, keys) if key in unseen_keys]
