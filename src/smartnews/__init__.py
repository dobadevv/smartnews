import logging
import os
from pathlib import Path

from smartnews.config import load_filter, load_notifiers, load_sources
from smartnews.fetching.rss import RssFetcher
from smartnews.filtering.factory import build_filter
from smartnews.notifiers.factory import build_notifiers
from smartnews.output import print_article
from smartnews.pipeline import stream_enabled_sources

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

    articles = stream_enabled_sources(sources, RssFetcher())
    article_filter = build_filter(load_filter(DEFAULT_CONFIG_PATH))

    if not notifiers:
        logger.info("no notifiers enabled; printing to stdout")
        for article in articles:
            print_article(article_filter.filter(article))
        logger.info("run complete")
        return

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL must be set when at least one notifier is enabled"
        )

    # Notifier dispatch is being rewired onto the generator pipeline across
    # Task 6 (dedup + notify streaming) and Task 7 (translation + final
    # wiring); this branch is completed by Task 7's rewrite.
    raise NotImplementedError(
        "notifier dispatch is being rewired for the generator pipeline"
    )
