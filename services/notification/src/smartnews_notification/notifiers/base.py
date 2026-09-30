from typing import Protocol

from smartnews_common.models import Article


class Notifier(Protocol):
    channel: str

    def send(self, article: Article) -> None: ...
