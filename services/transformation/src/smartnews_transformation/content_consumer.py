from smartnews_common.messages import ArticleCrawled
from smartnews_common.messaging.consumer import Consumer, ConsumerDeps
from smartnews_common.messaging.topology import ARTICLES_CRAWLED

from smartnews_transformation.config import FilterConfig
from smartnews_transformation.content_handler import (
    ContentRecorder,
    ContentTranslationHandler,
    ContentTranslationHandlerDeps,
)
from smartnews_transformation.filtering.factory import build_content_translator


def build_content_consumer(
    config: FilterConfig, rabbitmq_url: str, recorder: ContentRecorder
) -> Consumer[ArticleCrawled] | None:
    translator = build_content_translator(config)
    if translator is None:
        return None
    handler = ContentTranslationHandler(
        ContentTranslationHandlerDeps(translator=translator, recorder=recorder)
    )
    return Consumer(
        ConsumerDeps(
            rabbitmq_url=rabbitmq_url,
            queue=ARTICLES_CRAWLED,
            message_type=ArticleCrawled,
            handler=handler,
        )
    )
