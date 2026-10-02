import base64
import json
from dataclasses import dataclass
from datetime import datetime

from smartnews_common.db.catalog import MAX_ARTICLE_ID


class InvalidCursorError(ValueError):
    """The token was not produced by `encode_cursor`."""


@dataclass(frozen=True)
class PageCursor:
    """The `(sort_at, id)` position of the last article on a page."""

    sort_at: datetime
    article_id: int


def encode_cursor(cursor: PageCursor) -> str:
    payload = json.dumps(
        {"sort_at": cursor.sort_at.isoformat(), "id": cursor.article_id}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(token: str) -> PageCursor:
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        sort_at = datetime.fromisoformat(payload["sort_at"])
        article_id = payload["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidCursorError(f"cursor {token!r} is malformed") from error
    # A naive timestamp would be compared in the database session's time zone.
    if sort_at.tzinfo is None or not _is_article_id(article_id):
        raise InvalidCursorError(f"cursor {token!r} is malformed")
    return PageCursor(sort_at=sort_at, article_id=article_id)


def _is_article_id(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_ARTICLE_ID
