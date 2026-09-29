import logging
import os
from pathlib import Path

from smartnews.config import load_filter, load_notifiers, load_sources
from smartnews.fetching.rss import RssFetcher
from smartnews.filtering.factory import build_filter
from smartnews.notifiers.factory import build_notifiers
from smartnews.pipeline import (
    run_notify_pipeline,
    run_print_pipeline,
    stream_enabled_sources,
    stream_published_in_current_month,
    stream_translated,
    stream_unseen_capped_to_max_posts,
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

    fetched = stream_enabled_sources(sources, RssFetcher())
    articles = stream_published_in_current_month(fetched)
    article_filter = build_filter(load_filter(DEFAULT_CONFIG_PATH))

    if not notifiers:
        logger.info("no notifiers enabled; printing to stdout")
        run_print_pipeline(stream_translated(articles, article_filter))
        logger.info("run complete")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL must be set when at least one notifier is enabled"
        )

    logger.info("connecting to database")
    with PostgresSeenStore(database_url) as seen_store:
        seen_store.ensure_schema()
        capped = stream_unseen_capped_to_max_posts(
            articles, seen_store, notifiers, sources
        )
        translated = stream_translated(capped, article_filter)
        run_notify_pipeline(translated, notifiers, seen_store)
    logger.info("run complete")
