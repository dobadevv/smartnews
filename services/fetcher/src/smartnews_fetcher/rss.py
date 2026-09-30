import calendar
import re
from datetime import UTC, datetime

import feedparser
from smartnews_common.models import Article

from smartnews_fetcher.config import SourceConfig
from smartnews_fetcher.text import html_to_text


class RssFetcher:
    def fetch(self, source: SourceConfig) -> list[Article]:
        parsed = feedparser.parse(source.url)
        return [
            self._to_article(entry, source)
            for entry in parsed.entries
            # Without a link there is no URL to dedup on, and every such
            # entry would collapse onto the same hash.
            if entry.get("link")
        ]

    def _to_article(self, entry: dict, source: SourceConfig) -> Article:
        return Article(
            title=entry.get("title", ""),
            url=entry["link"],
            source=source.name,
            published_at=self._parse_published_at(entry),
            summary=html_to_text(entry.get("summary")),
            thumbnail=self._extract_thumbnail(entry),
            category=source.category,
        )

    def _parse_published_at(self, entry: dict) -> datetime | None:
        published_parsed = entry.get("published_parsed")
        if published_parsed is None:
            return None
        return datetime.fromtimestamp(
            calendar.timegm(published_parsed), tz=UTC
        )

    def _extract_thumbnail(self, entry: dict) -> str | None:
        # media:content with medium="image" or image type — e.g. High Scalability
        if "media_content" in entry:
            for media in entry.media_content:
                if media.get("medium") == "image" or media.get("type", "").startswith(
                    "image"
                ):
                    return media.get("url")

        # media:thumbnail (Media RSS) — common on many other feeds
        if "media_thumbnail" in entry:
            return entry.media_thumbnail[0].get("url")

        # enclosure with image type — e.g. Cloudflare, Smashing Magazine
        if "links" in entry:
            for link in entry.links:
                if link.get("rel") == "enclosure" and link.get("type", "").startswith(
                    "image"
                ):
                    return link.get("href")

        # itunes:image (podcast-style feeds)
        if "itunes_image" in entry:
            return entry.itunes_image.get("href")

        # Custom <image> tag inside item — e.g. TypeScript devblog
        image = entry.get("image")
        if isinstance(image, dict):
            return image.get("href") or image.get("url")

        # Fallback: scrape first <img> from content or summary — e.g. InfoQ, Node Weekly
        html = ""
        if "content" in entry and entry.content:
            html = entry.content[0].get("value", "")
        elif "summary" in entry:
            html = entry.summary

        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)

        return None
