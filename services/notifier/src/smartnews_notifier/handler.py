import logging
from collections.abc import Sequence
from typing import Protocol

from smartnews_common.messages import ArticleTransformed
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.models import Article

from smartnews_notifier.notifiers.base import Notifier

logger = logging.getLogger(__name__)


class DeliveryLedger(Protocol):
    def is_delivered(self, article_id: int, channel: str) -> bool: ...

    def mark_delivered(self, article_id: int, channel: str) -> None: ...


class DeliveryError(Exception):
    def __init__(self, article_id: int, failed_channels: list[str]) -> None:
        super().__init__(
            f"article {article_id} failed to send on: {', '.join(failed_channels)}"
        )
        self.article_id = article_id
        self.failed_channels = failed_channels


class NotificationHandler:
    def __init__(self, notifiers: Sequence[Notifier], ledger: DeliveryLedger) -> None:
        self._notifiers = notifiers
        self._ledger = ledger

    def __call__(self, message: ArticleTransformed, context: DeliveryContext) -> None:
        article = message.to_article()
        failed_channels = [
            notifier.channel
            for notifier in self._notifiers
            if not self._deliver(message.article_id, article, notifier)
        ]
        if failed_channels:
            raise DeliveryError(message.article_id, failed_channels)

    def _deliver(self, article_id: int, article: Article, notifier: Notifier) -> bool:
        if self._ledger.is_delivered(article_id, notifier.channel):
            return True
        try:
            notifier.send(article)
        except Exception:
            logger.exception(
                "failed to send article %d to %s: %s",
                article_id,
                notifier.channel,
                article.url,
            )
            return False
        self._ledger.mark_delivered(article_id, notifier.channel)
        return True
