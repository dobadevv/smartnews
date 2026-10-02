from smartnews_common.messages import ArticleCrawled
from smartnews_common.messaging.consumer import Consumer, ConsumerDeps
from smartnews_common.messaging.topology import ARTICLES_CRAWLED

from smartnews_transformer.config import LlmStepConfig
from smartnews_transformer.content_handler import (
    ContentRecorder,
    ContentTranslationHandler,
    ContentTranslationHandlerDeps,
)
from smartnews_transformer.filtering.factory import build_content_translator


def build_content_consumer(
    config: LlmStepConfig, rabbitmq_url: str, recorder: ContentRecorder
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
