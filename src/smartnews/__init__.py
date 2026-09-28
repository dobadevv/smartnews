import logging
import os
from pathlib import Path

from smartnews.config import load_notifiers, load_sources
from smartnews.fetching.rss import RssFetcher
from smartnews.notifiers.factory import build_notifiers
from smartnews.output import print_articles
from smartnews.pipeline import dispatch_to_notifiers, fetch_enabled_sources
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

    if not notifiers:
        logger.info("no notifiers enabled; printing to stdout")
        print_articles(articles)
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
    dispatch_to_notifiers(articles, notifiers, seen_store, sources)
    logger.info("run complete")
