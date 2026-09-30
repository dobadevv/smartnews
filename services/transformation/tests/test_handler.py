import logging

import pytest
from pydantic import BaseModel
from smartnews_common.messages import ArticleFetched, ArticleTransformed
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.messaging.topology import ARTICLES_TRANSFORMED
from smartnews_common.models import Article, Transformation
from smartnews_transformation.filtering.base import TransformationError
from smartnews_transformation.handler import (
    TransformationHandler,
    TransformationHandlerDeps,
)

TRANSLATION = Transformation(title="Tiêu đề", summary="Tóm tắt", language="vi")


class FakeFilter:
    def __init__(self, result: Transformation | None = TRANSLATION, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def transform(self, article: Article) -> Transformation | None:
        if self._error is not None:
            raise self._error
        return self._result


class RecordingRecorder:
    def __init__(self) -> None:
        self.recorded: list[tuple[int, Transformation]] = []

    def record(self, article_id: int, transformation: Transformation) -> None:
        self.recorded.append((article_id, transformation))


class RecordingPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, BaseModel]] = []

    def publish(self, routing_key: str, message: BaseModel) -> None:
        self.published.append((routing_key, message))


def make_fetched() -> ArticleFetched:
    article = Article(
        title="Hello", url="https://example.com/a", source="s", published_at=None, summary="S"
    )
    return ArticleFetched.from_article(article, article_id=5)


def run_handler(
    article_filter: FakeFilter, *, is_final_attempt: bool = False
) -> tuple[RecordingRecorder, RecordingPublisher]:
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = TransformationHandler(
        TransformationHandlerDeps(article_filter=article_filter, recorder=recorder)
    )
    context = DeliveryContext(
        attempt=4 if is_final_attempt else 1, is_final_attempt=is_final_attempt, publisher=publisher
    )
    handler(make_fetched(), context)
    return recorder, publisher


def test_handler_records_and_publishes_the_translation() -> None:
    recorder, publisher = run_handler(FakeFilter())

    assert recorder.recorded == [(5, TRANSLATION)]
    assert publisher.published == [
        (ARTICLES_TRANSFORMED, ArticleTransformed.translated(make_fetched(), TRANSLATION))
    ]


def test_handler_publishes_untranslated_without_recording_when_filter_is_disabled() -> None:
    recorder, publisher = run_handler(FakeFilter(result=None))

    assert recorder.recorded == []
    assert publisher.published == [
        (ARTICLES_TRANSFORMED, ArticleTransformed.untranslated(make_fetched()))
    ]


def test_handler_raises_for_a_retry_when_translation_fails_before_the_final_attempt() -> None:
    recorder, publisher = RecordingRecorder(), RecordingPublisher()
    handler = TransformationHandler(
        TransformationHandlerDeps(
            article_filter=FakeFilter(error=TransformationError("quota")), recorder=recorder
        )
    )

    with pytest.raises(TransformationError):
        handler(make_fetched(), DeliveryContext(attempt=1, is_final_attempt=False, publisher=publisher))

    assert (recorder.recorded, publisher.published) == ([], [])


def test_handler_forwards_untranslated_when_translation_fails_on_the_final_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        recorder, publisher = run_handler(
            FakeFilter(error=TransformationError("quota")), is_final_attempt=True
        )

    assert recorder.recorded == []
    assert publisher.published == [
        (ARTICLES_TRANSFORMED, ArticleTransformed.untranslated(make_fetched()))
    ]
    assert any("untranslated" in record.getMessage() for record in caplog.records)


def test_handler_does_not_swallow_unexpected_errors_on_the_final_attempt() -> None:
    with pytest.raises(KeyError):
        run_handler(FakeFilter(error=KeyError("bug")), is_final_attempt=True)
