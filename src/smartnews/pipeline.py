import logging
from collections.abc import Iterator

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.fetching.base import Fetcher
from smartnews.filtering.base import Filter
from smartnews.models import Article
from smartnews.notifiers.base import Notifier
from smartnews.output import print_article
from smartnews.repository.base import SeenStore

logger = logging.getLogger(__name__)


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


def stream_capped_to_max_posts(
    articles: Iterator[Article], sources: list[SourceConfig]
) -> Iterator[Article]:
    max_posts_by_source = _max_posts_by_source(sources)
    sent_count_by_source: dict[str, int] = {}
    for article in articles:
        max_posts = max_posts_by_source.get(article.source)
        if max_posts is None:
            yield article
            continue
        sent_count = sent_count_by_source.get(article.source, 0)
        if sent_count < max_posts:
            yield article
            sent_count_by_source[article.source] = sent_count + 1


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


def stream_translated(
    articles: Iterator[Article], article_filter: Filter
) -> Iterator[Article]:
    for article in articles:
        yield article_filter.filter(article)


def run_print_pipeline(articles: Iterator[Article]) -> None:
    for article in articles:
        print_article(article)


def _max_posts_by_source(sources: list[SourceConfig]) -> dict[str, int]:
    return {
        source.name: source.max_posts
        for source in sources
        if source.max_posts is not None
    }
