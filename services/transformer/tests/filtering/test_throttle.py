from smartnews_common.models import Article, Transformation
from smartnews_transformer.filtering.throttle import (
    Throttle,
    ThrottledContentTranslator,
    ThrottledFilter,
)

ARTICLE = Article(
    source="example",
    title="Title",
    url="https://example.com/a",
    summary="Summary",
    published_at=None,
)
TRANSFORMATION = Transformation(language="vi", title="Tiêu đề", summary="Tóm tắt")


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def build_throttle(clock: FakeClock, delay_seconds: float) -> Throttle:
    return Throttle(
        delay_seconds=delay_seconds, monotonic=clock.monotonic, sleep=clock.sleep
    )


def test_throttle_does_not_wait_before_the_first_call() -> None:
    clock = FakeClock()
    throttle = build_throttle(clock, delay_seconds=3)

    throttle.wait()

    assert clock.sleeps == []


def test_throttle_waits_out_the_delay_between_back_to_back_calls() -> None:
    clock = FakeClock()
    throttle = build_throttle(clock, delay_seconds=3)
    throttle.wait()

    throttle.wait()

    assert clock.sleeps == [3]


def test_throttle_waits_only_for_the_remainder_of_the_delay() -> None:
    clock = FakeClock()
    throttle = build_throttle(clock, delay_seconds=3)
    throttle.wait()
    clock.now += 1

    throttle.wait()

    assert clock.sleeps == [2]


def test_throttle_does_not_wait_once_the_delay_has_passed() -> None:
    clock = FakeClock()
    throttle = build_throttle(clock, delay_seconds=3)
    throttle.wait()
    clock.now += 5

    throttle.wait()

    assert clock.sleeps == []


class RecordingFilter:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.called_at: list[float] = []

    def transform(self, article: Article) -> Transformation | None:
        self.called_at.append(self._clock.now)
        return TRANSFORMATION


class RecordingTranslator:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.called_at: list[float] = []

    def translate(self, content: str) -> str:
        self.called_at.append(self._clock.now)
        return f"translated {content}"


def test_throttled_filter_spaces_out_calls_to_the_wrapped_filter() -> None:
    clock = FakeClock()
    inner = RecordingFilter(clock)
    throttled = ThrottledFilter(
        article_filter=inner, throttle=build_throttle(clock, delay_seconds=3)
    )

    results = [throttled.transform(ARTICLE), throttled.transform(ARTICLE)]

    assert results == [TRANSFORMATION, TRANSFORMATION]
    assert inner.called_at == [100.0, 103.0]


def test_throttled_content_translator_spaces_out_calls_to_the_wrapped_one() -> None:
    clock = FakeClock()
    inner = RecordingTranslator(clock)
    throttled = ThrottledContentTranslator(
        translator=inner, throttle=build_throttle(clock, delay_seconds=3)
    )

    results = [throttled.translate("a"), throttled.translate("b")]

    assert results == ["translated a", "translated b"]
    assert inner.called_at == [100.0, 103.0]
