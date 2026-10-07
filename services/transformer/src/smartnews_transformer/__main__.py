import logging
from pathlib import Path

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.consumer import Consumer
from smartnews_common.messaging.consumer_group import ConsumerGroup, RunnableConsumer
from smartnews_common.messaging.topology import ARTICLES_FETCHED, ARTICLES_TRANSFORMED
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_transformer.config import load_transformation_config
from smartnews_transformer.content_consumer import build_content_consumer
from smartnews_transformer.filtering.factory import build_filter
from smartnews_transformer.handler import TransformationHandler
from smartnews_transformer.recording import DatabaseTransformationRecorder

DEFAULT_CONFIG_PATH = Path("config/transformer.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_transformation_config(DEFAULT_CONFIG_PATH)
    rabbitmq_url = require_env("RABBITMQ_URL")
    recorder = DatabaseTransformationRecorder(
        create_database_engine(require_env("DATABASE_URL"))
    )
    handler = TransformationHandler(
        article_filter=build_filter(config.summary), recorder=recorder
    )
    consumers: list[RunnableConsumer] = [
        Consumer(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_FETCHED,
            message_type=ArticleFetched,
            handler=handler,
            output_queues=(ARTICLES_TRANSFORMED,),
        )
    ]
    content_consumer = build_content_consumer(
        config=config.content, rabbitmq_url=rabbitmq_url, recorder=recorder
    )
    if content_consumer is not None:
        consumers.append(content_consumer)
    group = ConsumerGroup(consumers)
    call_on_shutdown_signals(group.stop)
    logger.info(
        "transformation started: summary enabled=%s provider=%s, "
        "content enabled=%s provider=%s, consumers=%d, run_once=%s",
        config.summary.enabled,
        config.summary.provider,
        config.content.enabled,
        config.content.provider,
        len(consumers),
        config.run_once,
    )
    if config.run_once:
        group.consume_one()
    else:
        group.run()
    logger.info("transformation stopped")


if __name__ == "__main__":
    main()
