from typing import Protocol

from smartnews.models import Article


class Filter(Protocol):
    def filter(self, articles: list[Article]) -> list[Article]: ...
