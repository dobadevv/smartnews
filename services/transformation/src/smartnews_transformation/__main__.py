import logging
from pathlib import Path

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.consumer import Consumer, ConsumerDeps
from smartnews_common.messaging.topology import ARTICLES_FETCHED, ARTICLES_TRANSFORMED
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_transformation.config import load_transformation_config
from smartnews_transformation.filtering.factory import build_filter
from smartnews_transformation.handler import (
    TransformationHandler,
    TransformationHandlerDeps,
)
from smartnews_transformation.recording import DatabaseTransformationRecorder

DEFAULT_CONFIG_PATH = Path("config/transformation.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_transformation_config(DEFAULT_CONFIG_PATH)
    handler = TransformationHandler(
        TransformationHandlerDeps(
            article_filter=build_filter(config.filter),
            recorder=DatabaseTransformationRecorder(
                create_database_engine(require_env("DATABASE_URL"))
            ),
        )
    )
    consumer = Consumer(
        ConsumerDeps(
            rabbitmq_url=require_env("RABBITMQ_URL"),
            queue=ARTICLES_FETCHED,
            message_type=ArticleFetched,
            handler=handler,
            output_queues=(ARTICLES_TRANSFORMED,),
        )
    )
    call_on_shutdown_signals(consumer.stop)
    logger.info(
        "transformation started: filter enabled=%s provider=%s",
        config.filter.enabled,
        config.filter.provider,
    )
    consumer.run()
    logger.info("transformation stopped")


if __name__ == "__main__":
    main()
