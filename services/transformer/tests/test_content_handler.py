import pytest
from pydantic import BaseModel
from smartnews_common.messages import ArticleCrawled, ArticleFetched
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.models import Article
from smartnews_transformer.content_handler import ContentTranslationHandler
from smartnews_transformer.filtering.base import TransformationError


class FakeTranslator:
    def __init__(self, result: str = "Nội dung", error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.translated: list[str] = []

    def translate(self, content: str) -> str:
        if self._error is not None:
            raise self._error
        self.translated.append(content)
        return self._result


class RecordingContentRecorder:
    def __init__(self) -> None:
        self.recorded: list[tuple[int, str]] = []

    def record_content(self, article_id: int, content: str) -> None:
        self.recorded.append((article_id, content))


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, BaseModel]] = []

    def publish(self, routing_key: str, message: BaseModel) -> None:
        self.published.append((routing_key, message))


def make_crawled() -> ArticleCrawled:
    article = Article(
        title="Hello", url="https://example.com/a", source="s", published_at=None, summary="S"
    )
    return ArticleCrawled.from_fetched(
        ArticleFetched.from_article(article, article_id=5), content="Original content"
    )


def make_handler(
    translator: FakeTranslator, recorder: RecordingContentRecorder
) -> ContentTranslationHandler:
    return ContentTranslationHandler(translator=translator, recorder=recorder)


def make_context(publisher: RecordingPublisher, *, is_final_attempt: bool = False) -> DeliveryContext:
    return DeliveryContext(
        attempt=4 if is_final_attempt else 1,
        is_final_attempt=is_final_attempt,
        publisher=publisher,
    )


def test_handler_records_the_translated_content_without_publishing() -> None:
    translator, recorder, publisher = FakeTranslator("Nội dung"), RecordingContentRecorder(), RecordingPublisher()

    make_handler(translator, recorder)(make_crawled(), make_context(publisher))

    assert translator.translated == ["Original content"]
    assert recorder.recorded == [(5, "Nội dung")]
    assert publisher.published == []


@pytest.mark.parametrize("is_final_attempt", [False, True])
def test_handler_raises_and_records_nothing_when_translation_fails(
    is_final_attempt: bool,
) -> None:
    recorder, publisher = RecordingContentRecorder(), RecordingPublisher()
    handler = make_handler(FakeTranslator(error=TransformationError("quota")), recorder)

    with pytest.raises(TransformationError):
        handler(make_crawled(), make_context(publisher, is_final_attempt=is_final_attempt))

    assert (recorder.recorded, publisher.published) == ([], [])
