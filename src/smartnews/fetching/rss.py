import feedparser

from smartnews.config import SourceConfig
from smartnews.models import Article


class RssFetcher:
    def fetch(self, source: SourceConfig) -> list[Article]:
        parsed = feedparser.parse(source.url)
        return [
            Article(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source=source.name,
                published_at=entry.get("published"),
                summary=entry.get("summary"),
            )
            for entry in parsed.entries
        ]
