import logging
from pathlib import Path

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.consumer import Consumer, ConsumerDeps
from smartnews_common.messaging.topology import (
    ARTICLES_CRAWLED,
    ARTICLES_FETCHED,
    ARTICLES_TO_CRAWL,
)
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_crawler.config import load_crawler_config
from smartnews_crawler.extraction.registry import ExtractorRegistry
from smartnews_crawler.fetching.http import HttpPageFetcher
from smartnews_crawler.handler import CrawlerHandler, CrawlerHandlerDeps
from smartnews_crawler.recording import DatabaseContentRecorder

DEFAULT_CONFIG_PATH = Path("config/crawler.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_crawler_config(DEFAULT_CONFIG_PATH)
    handler = CrawlerHandler(
        CrawlerHandlerDeps(
            fetcher=HttpPageFetcher(
                timeout_seconds=config.timeout_seconds, user_agent=config.user_agent
            ),
            extractors=ExtractorRegistry(config),
            recorder=DatabaseContentRecorder(create_database_engine(require_env("DATABASE_URL"))),
        )
    )
    consumer = Consumer(
        ConsumerDeps(
            rabbitmq_url=require_env("RABBITMQ_URL"),
            queue=ARTICLES_TO_CRAWL,
            message_type=ArticleFetched,
            handler=handler,
            input_routing_key=ARTICLES_FETCHED,
            output_queues=(ARTICLES_CRAWLED,),
        )
    )
    call_on_shutdown_signals(consumer.stop)
    logger.info(
        "crawler started: consuming %s (fanned out from %s)", ARTICLES_TO_CRAWL, ARTICLES_FETCHED
    )
    consumer.run()
    logger.info("crawler stopped")


if __name__ == "__main__":
    main()
