import logging

from smartnews.config import SourceConfig
from smartnews.dedup import article_key
from smartnews.fetching.base import Fetcher
from smartnews.models import Article
from smartnews.notifiers.base import Notifier
from smartnews.repository.base import SeenStore

logger = logging.getLogger(__name__)


def fetch_enabled_sources(
    sources: list[SourceConfig], fetcher: Fetcher
) -> list[Article]:
    articles: list[Article] = []
    for source in sources:
        if not source.enabled:
            continue
        fetched = fetcher.fetch(source)
        logger.info("fetched %d article(s) from %s", len(fetched), source.name)
        articles.extend(fetched)
    logger.info(
        "fetch complete: %d article(s) from %d source(s)",
        len(articles),
        sum(1 for source in sources if source.enabled),
    )
    return articles


def filter_unseen_articles(
    articles: list[Article], seen_store: SeenStore, channel: str
) -> list[Article]:
    keys = [article_key(article) for article in articles]
    unseen_keys = seen_store.filter_unseen(keys, channel)
    return [article for article, key in zip(articles, keys) if key in unseen_keys]


def select_unseen_for_any_channel(
    articles: list[Article], seen_store: SeenStore, notifiers: list[Notifier]
) -> list[Article]:
    if not notifiers:
        return list(articles)
    keys = [article_key(article) for article in articles]
    unseen_keys: set[str] = set()
    for notifier in notifiers:
        unseen_keys |= seen_store.filter_unseen(keys, notifier.channel)
    return [article for article, key in zip(articles, keys) if key in unseen_keys]


def limit_to_minimum_posts(
    articles: list[Article], sources: list[SourceConfig]
) -> list[Article]:
    return _limit_to_minimum_posts(articles, _minimum_posts_by_source(sources))


def dispatch_to_notifiers(
    articles: list[Article],
    notifiers: list[Notifier],
    seen_store: SeenStore,
    sources: list[SourceConfig],
) -> None:
    minimum_posts_by_source = _minimum_posts_by_source(sources)
    for notifier in notifiers:
        unseen = filter_unseen_articles(articles, seen_store, notifier.channel)
        batch = _limit_to_minimum_posts(unseen, minimum_posts_by_source)
        if not batch:
            logger.info("nothing to send to %s", notifier.channel)
            continue
        sent_count = _send_and_mark_seen(batch, notifier, seen_store)
        logger.info(
            "sent %d/%d article(s) to %s", sent_count, len(batch), notifier.channel
        )


def _send_and_mark_seen(
    articles: list[Article], notifier: Notifier, seen_store: SeenStore
) -> int:
    sent_count = 0
    for article in articles:
        try:
            notifier.send([article])
        except Exception:
            logger.exception(
                "failed to send article to %s: %s", notifier.channel, article.url
            )
            continue
        seen_store.mark_seen(article_key(article), notifier.channel)
        sent_count += 1
    return sent_count


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
