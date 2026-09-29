import logging
from collections.abc import Iterator

from smartnews.config import SourceConfig
from smartnews.fetching.base import Fetcher
from smartnews.models import Article

logger = logging.getLogger(__name__)


def stream_enabled_sources(
    sources: list[SourceConfig], fetcher: Fetcher
) -> Iterator[Article]:
    minimum_posts_by_source = _minimum_posts_by_source(sources)
    for source in sources:
        if not source.enabled:
            continue
        try:
            fetched = fetcher.fetch(source)
        except Exception:
            logger.exception("failed to fetch source %s", source.name)
            continue
        capped = _limit_to_minimum_posts(fetched, minimum_posts_by_source)
        logger.info(
            "fetched %d article(s) from %s (%d after cap)",
            len(fetched),
            source.name,
            len(capped),
        )
        yield from capped


def _minimum_posts_by_source(sources: list[SourceConfig]) -> dict[str, int]:
    return {
        source.name: source.minimum_posts
        for source in sources
        if source.minimum_posts is not None
    }


def _limit_to_minimum_posts(
    articles: list[Article], minimum_posts_by_source: dict[str, int]
) -> list[Article]:
    sent_count_by_source: dict[str, int] = {}
    limited_articles: list[Article] = []
    for article in articles:
        minimum_posts = minimum_posts_by_source.get(article.source)
        if minimum_posts is None:
            limited_articles.append(article)
            continue
        sent_count = sent_count_by_source.get(article.source, 0)
        if sent_count < minimum_posts:
            limited_articles.append(article)
            sent_count_by_source[article.source] = sent_count + 1
    return limited_articles
