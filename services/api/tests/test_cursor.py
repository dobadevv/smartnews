import base64
import json
import re
from datetime import UTC, datetime, timedelta, timezone

import pytest
from smartnews_api.cursor import (
    InvalidCursorError,
    PageCursor,
    decode_cursor,
    encode_cursor,
)

VALID_SORT_AT = "2026-01-01T00:00:00+00:00"


def token_for(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param(
            PageCursor(sort_at=datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC), article_id=42),
            id="utc with microseconds",
        ),
        pytest.param(
            PageCursor(sort_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=7))), article_id=1),
            id="non-utc offset",
        ),
        pytest.param(
            PageCursor(sort_at=datetime(2026, 1, 1, tzinfo=UTC), article_id=2**63 - 1),
            id="largest article id",
        ),
    ],
)
def test_decode_cursor_reverses_encode_cursor(cursor: PageCursor) -> None:
    assert decode_cursor(encode_cursor(cursor)) == cursor


def test_encode_cursor_produces_a_url_safe_token() -> None:
    token = encode_cursor(PageCursor(sort_at=datetime(2026, 1, 1, tzinfo=UTC), article_id=42))

    assert re.fullmatch(r"[A-Za-z0-9_-]+", token)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("%%%", id="not base64"),
        pytest.param("éé", id="non-ascii"),
        pytest.param(token_for([1, 2]), id="not an object"),
        pytest.param(token_for({"id": 1}), id="missing sort_at"),
        pytest.param(token_for({"sort_at": VALID_SORT_AT}), id="missing id"),
        pytest.param(token_for({"sort_at": "yesterday", "id": 1}), id="unparseable sort_at"),
        pytest.param(token_for({"sort_at": 5, "id": 1}), id="sort_at not a string"),
        pytest.param(token_for({"sort_at": "2026-01-01T00:00:00", "id": 1}), id="sort_at without offset"),
        pytest.param(token_for({"sort_at": VALID_SORT_AT, "id": "1"}), id="id not an integer"),
        pytest.param(token_for({"sort_at": VALID_SORT_AT, "id": True}), id="id boolean"),
        pytest.param(token_for({"sort_at": VALID_SORT_AT, "id": 0}), id="id zero"),
        pytest.param(token_for({"sort_at": VALID_SORT_AT, "id": 2**63}), id="id beyond bigint"),
    ],
)
def test_decode_cursor_rejects_malformed_tokens(token: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(token)
