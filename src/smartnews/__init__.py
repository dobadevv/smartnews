import logging
import os
from pathlib import Path

from smartnews.config import load_filter, load_notifiers, load_sources
from smartnews.fetching.rss import RssFetcher
from smartnews.filtering.factory import build_filter
from smartnews.notifiers.factory import build_notifiers
from smartnews.output import print_articles
from smartnews.pipeline import (
    dispatch_to_notifiers,
    fetch_enabled_sources,
    limit_to_minimum_posts,
    select_unseen_for_any_channel,
)
from smartnews.repository.postgres import PostgresSeenStore

DEFAULT_CONFIG_PATH = Path("config/sources.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    logger.info("starting smartnews run")

    sources = load_sources(DEFAULT_CONFIG_PATH)
    notifiers = build_notifiers(load_notifiers(DEFAULT_CONFIG_PATH))
    logger.info(
        "loaded %d source(s) (%d enabled), %d notifier(s): %s",
        len(sources),
        sum(1 for source in sources if source.enabled),
        len(notifiers),
        [notifier.channel for notifier in notifiers],
    )

    articles = fetch_enabled_sources(sources, RssFetcher())
    article_filter = build_filter(load_filter(DEFAULT_CONFIG_PATH))

    if not notifiers:
        logger.info("no notifiers enabled; printing to stdout")
        print_articles(article_filter.filter(articles))
        logger.info("run complete")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL must be set when at least one notifier is enabled"
        )

    logger.info("connecting to database")
    seen_store = PostgresSeenStore(database_url)
    seen_store.ensure_schema()

    unseen_articles = select_unseen_for_any_channel(articles, seen_store, notifiers)
    capped_articles = limit_to_minimum_posts(unseen_articles, sources)
    logger.info(
        "%d/%d unseen article(s) need translation after applying per-source limits",
        len(capped_articles),
        len(unseen_articles),
    )
    translated_articles = article_filter.filter(capped_articles)
    dispatch_to_notifiers(translated_articles, notifiers, seen_store, sources)
    logger.info("run complete")
