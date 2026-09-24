from typing import Protocol

from smartnews.config import SourceConfig
from smartnews.models import Article


class Fetcher(Protocol):
    def fetch(self, source: SourceConfig) -> list[Article]: ...
