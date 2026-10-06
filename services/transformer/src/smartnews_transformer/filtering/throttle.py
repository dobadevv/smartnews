import time
from collections.abc import Callable

from smartnews_common.models import Article, Transformation

from smartnews_transformer.filtering.base import ContentTranslator, Filter


class Throttle:
    """Keep consecutive provider calls at least ``delay_seconds`` apart.

    Spacing out requests keeps a burst of queued articles under the
    provider's rate limit instead of tripping it and burning retries.
    """

    def __init__(
        self,
        delay_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._delay_seconds = delay_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_call_at: float | None = None

    def wait(self) -> None:
        if self._last_call_at is not None:
            remaining = self._last_call_at + self._delay_seconds - self._monotonic()
            if remaining > 0:
                self._sleep(remaining)
        self._last_call_at = self._monotonic()


class ThrottledFilter:
    def __init__(self, article_filter: Filter, throttle: Throttle) -> None:
        self._filter = article_filter
        self._throttle = throttle

    def transform(self, article: Article) -> Transformation | None:
        self._throttle.wait()
        return self._filter.transform(article)


class ThrottledContentTranslator:
    def __init__(self, translator: ContentTranslator, throttle: Throttle) -> None:
        self._translator = translator
        self._throttle = throttle

    def translate(self, content: str) -> str:
        self._throttle.wait()
        return self._translator.translate(content)
