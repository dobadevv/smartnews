import logging
from typing import Protocol

from smartnews_common.messages import ArticleFetched, ArticleTransformed
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.messaging.topology import ARTICLES_TRANSFORMED
from smartnews_common.models import Transformation

from smartnews_transformer.filtering.base import Filter, TransformationError

logger = logging.getLogger(__name__)


class TransformationRecorder(Protocol):
    def record(self, article_id: int, transformation: Transformation) -> None: ...


class TransformationHandler:
    def __init__(self, article_filter: Filter, recorder: TransformationRecorder) -> None:
        self._filter = article_filter
        self._recorder = recorder

    def __call__(self, message: ArticleFetched, context: DeliveryContext) -> None:
        context.publisher.publish(ARTICLES_TRANSFORMED, self._transform(message, context))

    def _transform(
        self, message: ArticleFetched, context: DeliveryContext
    ) -> ArticleTransformed:
        try:
            transformation = self._filter.transform(message.to_article())
        except TransformationError:
            if not context.is_final_attempt:
                raise
            # Out of retries: an untranslated article beats a dropped one.
            logger.exception(
                "translation failed after %d attempts; forwarding %s untranslated",
                context.attempt,
                message.url,
            )
            return ArticleTransformed.untranslated(message)
        if transformation is None:
            return ArticleTransformed.untranslated(message)
        self._recorder.record(message.article_id, transformation)
        return ArticleTransformed.translated(message, transformation)
