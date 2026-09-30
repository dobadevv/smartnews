import logging
from pathlib import Path

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.messages import ArticleTransformed
from smartnews_common.messaging.consumer import Consumer, ConsumerDeps
from smartnews_common.messaging.topology import ARTICLES_TRANSFORMED
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_notification.config import load_notification_config
from smartnews_notification.handler import NotificationHandler, NotificationHandlerDeps
from smartnews_notification.ledger import DatabaseDeliveryLedger
from smartnews_notification.notifiers.factory import build_notifiers

DEFAULT_CONFIG_PATH = Path("config/notification.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    notifiers = build_notifiers(load_notification_config(DEFAULT_CONFIG_PATH).notifiers)
    if not notifiers:
        logger.warning("no notifier enabled; articles will be acknowledged without sending")
    handler = NotificationHandler(
        NotificationHandlerDeps(
            notifiers=notifiers,
            ledger=DatabaseDeliveryLedger(
                create_database_engine(require_env("DATABASE_URL"))
            ),
        )
    )
    consumer = Consumer(
        ConsumerDeps(
            rabbitmq_url=require_env("RABBITMQ_URL"),
            queue=ARTICLES_TRANSFORMED,
            message_type=ArticleTransformed,
            handler=handler,
        )
    )
    call_on_shutdown_signals(consumer.stop)
    logger.info("notification started: channels=%s", [n.channel for n in notifiers])
    consumer.run()
    logger.info("notification stopped")


if __name__ == "__main__":
    main()
