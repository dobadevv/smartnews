from typing import Protocol

from smartnews.models import Article


class Notifier(Protocol):
    channel: str

    def send(self, articles: list[Article]) -> None: ...
