from typing import Protocol

from smartnews_common.messages import ArticleCrawled
from smartnews_common.messaging.consumer import DeliveryContext

from smartnews_transformer.filtering.base import ContentTranslator
from smartnews_transformer.step_logging import logged_step


class ContentRecorder(Protocol):
    def record_content(self, article_id: int, content: str) -> None: ...


class ContentTranslationHandler:
    """Translates a crawled article's content and stores it.

    Publishes nothing: articles.transformed already carries the article to
    notification, and a second message would post it twice.
    """

    def __init__(self, translator: ContentTranslator, recorder: ContentRecorder) -> None:
        self._translator = translator
        self._recorder = recorder

    def __call__(self, message: ArticleCrawled, context: DeliveryContext) -> None:
        with logged_step("translate content", message.article_id):
            translated = self._translator.translate(message.content)
        with logged_step("save translated content", message.article_id):
            self._recorder.record_content(message.article_id, translated)
