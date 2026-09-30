import logging
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Protocol

from smartnews_common.models import Article

from smartnews_fetcher.config import SourceConfig

DEFAULT_LOOKBACK_DAYS = 7

logger = logging.getLogger(__name__)


class Fetcher(Protocol):
    def fetch(self, source: SourceConfig) -> list[Article]: ...


class NewArticlePublisher(Protocol):
    def publish_if_new(self, article: Article) -> bool:
        """Persist and publish the article if its URL is unseen; return whether it was."""
        ...


def stream_enabled_sources(
    sources: list[SourceConfig], fetcher: Fetcher
) -> Iterator[Article]:
    for source in sources:
        if not source.enabled:
            continue
        try:
            fetched = fetcher.fetch(source)
        except Exception:
            logger.exception("failed to fetch source %s", source.name)
            continue
        logger.info("fetched %d article(s) from %s", len(fetched), source.name)
        yield from fetched


def stream_published_within_lookback_days(
    articles: Iterable[Article],
    sources: list[SourceConfig],
    now: datetime | None = None,
) -> Iterator[Article]:
    current = now or datetime.now(UTC)
    lookback_days_by_source = {source.name: source.lookback_days for source in sources}
    for article in articles:
        published_at = article.published_at
        if published_at is None:
            yield article
            continue
        lookback_days = lookback_days_by_source.get(article.source, DEFAULT_LOOKBACK_DAYS)
        if current - published_at <= timedelta(days=lookback_days):
            yield article


def stream_new_capped_to_max_posts(
    articles: Iterable[Article],
    sources: list[SourceConfig],
    publisher: NewArticlePublisher,
) -> Iterator[Article]:
    max_posts_by_source = {
        source.name: source.max_posts for source in sources if source.max_posts is not None
    }
    new_count_by_source: dict[str, int] = {}
    for article in articles:
        max_posts = max_posts_by_source.get(article.source)
        new_count = new_count_by_source.get(article.source, 0)
        if max_posts is not None and new_count >= max_posts:
            # Cap already filled: skip without a database round trip.
            continue
        if not publisher.publish_if_new(article):
            continue
        new_count_by_source[article.source] = new_count + 1
        yield article
