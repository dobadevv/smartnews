from dataclasses import dataclass
from typing import Protocol

from smartnews_common.messages import ArticleCrawled
from smartnews_common.messaging.consumer import DeliveryContext

from smartnews_transformation.filtering.base import ContentTranslator


class ContentRecorder(Protocol):
    def record_content(self, article_id: int, content: str) -> None: ...


@dataclass(frozen=True)
class ContentTranslationHandlerDeps:
    translator: ContentTranslator
    recorder: ContentRecorder


class ContentTranslationHandler:
    """Translates a crawled article's content and stores it.

    Publishes nothing: articles.transformed already carries the article to
    notification, and a second message would post it twice.
    """

    def __init__(self, deps: ContentTranslationHandlerDeps) -> None:
        self._translator = deps.translator
        self._recorder = deps.recorder

    def __call__(self, message: ArticleCrawled, context: DeliveryContext) -> None:
        translated = self._translator.translate(message.content)
        self._recorder.record_content(message.article_id, translated)
