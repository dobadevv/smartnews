import logging
from typing import Protocol

from smartnews_common.messages import ArticleFetched, ArticleTransformed
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.messaging.topology import ARTICLES_TRANSFORMED
from smartnews_common.models import Transformation

from smartnews_transformer.filtering.base import Filter, TransformationError
from smartnews_transformer.step_logging import logged_step

logger = logging.getLogger(__name__)


class TransformationRecorder(Protocol):
    def record(self, article_id: int, transformation: Transformation) -> None: ...


class TransformationHandler:
    def __init__(self, article_filter: Filter, recorder: TransformationRecorder) -> None:
        self._filter = article_filter
        self._recorder = recorder

    def __call__(self, message: ArticleFetched, context: DeliveryContext) -> None:
        transformed = self._transform(message, context)
        with logged_step(f"publish to {ARTICLES_TRANSFORMED}", message.article_id):
            context.publisher.publish(ARTICLES_TRANSFORMED, transformed)

    def _transform(
        self, message: ArticleFetched, context: DeliveryContext
    ) -> ArticleTransformed:
        try:
            with logged_step("translate summary", message.article_id):
                transformation = self._filter.transform(message.to_article())
        except TransformationError:
            if not context.is_final_attempt:
                raise
            # Out of retries: an untranslated article beats a dropped one.
            logger.exception(
                "translation failed after %d attempts; forwarding article_id=%d "
                "(%s) untranslated",
                context.attempt,
                message.article_id,
                message.url,
            )
            return ArticleTransformed.untranslated(message)
        if transformation is None:
            logger.info(
                "summary translation disabled; forwarding article_id=%d untranslated",
                message.article_id,
            )
            return ArticleTransformed.untranslated(message)
        with logged_step("save transformation", message.article_id):
            self._recorder.record(message.article_id, transformation)
        return ArticleTransformed.translated(message, transformation)
