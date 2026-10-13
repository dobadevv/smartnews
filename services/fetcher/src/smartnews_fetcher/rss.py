import calendar
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import feedparser
from smartnews_common.models import Article

from smartnews_fetcher.config import SourceConfig
from smartnews_fetcher.text import html_to_text

# feedparser does not recognise month-first 12-hour dates without an offset,
# e.g. Tuoi Tre's "10/8/2026 2:06:00\u202fPM".
MONTH_FIRST_DATE_FORMAT = "%m/%d/%Y %I:%M:%S %p"


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
            published_at=self._parse_published_at(entry, source),
            summary=html_to_text(entry.get("summary")),
            thumbnail=self._extract_thumbnail(entry),
            category=source.category,
        )

    def _parse_published_at(self, entry: dict, source: SourceConfig) -> datetime | None:
        # GitHub release (Atom) feeds carry only <updated>.
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed is not None:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        return self._parse_month_first_date(entry.get("published"), source)

    def _parse_month_first_date(
        self, raw: str | None, source: SourceConfig
    ) -> datetime | None:
        if not raw:
            return None
        try:
            local = datetime.strptime(
                " ".join(raw.split()), MONTH_FIRST_DATE_FORMAT
            ).replace(tzinfo=ZoneInfo(source.timezone))
        except ValueError:
            return None
        return local.astimezone(UTC)

    def _extract_thumbnail(self, entry: dict) -> str | None:
        # media:content with medium="image" or image type — e.g. High Scalability
        if "media_content" in entry:
            for media in entry["media_content"]:
                if media.get("medium") == "image" or media.get("type", "").startswith(
                    "image"
                ):
                    return media.get("url")

        # media:thumbnail (Media RSS) — common on many other feeds
        if "media_thumbnail" in entry:
            return entry["media_thumbnail"][0].get("url")

        # enclosure with image type — e.g. Cloudflare, Smashing Magazine
        if "links" in entry:
            for link in entry["links"]:
                if link.get("rel") == "enclosure" and link.get("type", "").startswith(
                    "image"
                ):
                    return link.get("href")

        # itunes:image (podcast-style feeds)
        if "itunes_image" in entry:
            return entry["itunes_image"].get("href")

        # Custom <image> tag inside item — e.g. TypeScript devblog
        image = entry.get("image")
        if isinstance(image, dict):
            return image.get("href") or image.get("url")

        # Fallback: scrape first <img> from content or summary — e.g. InfoQ, Node Weekly
        html = ""
        if entry.get("content"):
            html = entry["content"][0].get("value", "")
        elif "summary" in entry:
            html = entry["summary"]

        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)

        return None
