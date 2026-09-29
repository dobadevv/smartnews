import logging
from collections.abc import Iterator

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.fetching.base import Fetcher
from smartnews.models import Article
from smartnews.notifiers.base import Notifier
from smartnews.repository.base import SeenStore

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


def stream_unseen_for_any_channel(
    articles: Iterator[Article], seen_store: SeenStore, notifiers: list[Notifier]
) -> Iterator[Article]:
    if not notifiers:
        yield from articles
        return
    for article in articles:
        key = article_key(article)
        if any(
            not seen_store.is_seen(key, notifier.channel) for notifier in notifiers
        ):
            yield article


def run_notify_pipeline(
    articles: Iterator[Article], notifiers: list[Notifier], seen_store: SeenStore
) -> None:
    candidate_counts = {notifier.channel: 0 for notifier in notifiers}
    sent_counts = {notifier.channel: 0 for notifier in notifiers}
    for article in articles:
        key = article_key(article)
        for notifier in notifiers:
            if seen_store.is_seen(key, notifier.channel):
                continue
            candidate_counts[notifier.channel] += 1
            if _send_and_mark(article, key, notifier, seen_store):
                sent_counts[notifier.channel] += 1
    for notifier in notifiers:
        logger.info(
            "sent %d/%d article(s) to %s",
            sent_counts[notifier.channel],
            candidate_counts[notifier.channel],
            notifier.channel,
        )


def _send_and_mark(
    article: Article, key: str, notifier: Notifier, seen_store: SeenStore
) -> bool:
    try:
        notifier.send(article)
    except Exception:
        logger.exception(
            "failed to send article to %s: %s", notifier.channel, article.url
        )
        return False
    seen_store.mark_seen(key, notifier.channel)
    return True


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
