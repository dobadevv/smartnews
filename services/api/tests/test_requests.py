from datetime import UTC, datetime

import pytest
from smartnews_api.cursor import PageCursor, encode_cursor
from smartnews_api.language import Language
from smartnews_api.requests import (
    InvalidRequestError,
    PageSizeLimits,
    parse_detail_query,
    parse_list_query,
)

LIMITS = PageSizeLimits(default=20, maximum=100)
CURSOR = PageCursor(sort_at=datetime(2026, 1, 1, tzinfo=UTC), article_id=5)


def test_parse_list_query_reads_every_parameter() -> None:
    query = parse_list_query(
        {
            "lang": "vi",
            "limit": "5",
            "category": "tech",
            "source": "vnexpress",
            "cursor": encode_cursor(CURSOR),
        },
        LIMITS,
    )

    assert (query.lang, query.limit, query.category, query.source, query.cursor) == (
        Language.VIETNAMESE, 5, "tech", "vnexpress", CURSOR
    )


def test_parse_list_query_applies_defaults_when_only_language_is_given() -> None:
    query = parse_list_query({"lang": "en"}, LIMITS)

    assert (query.limit, query.category, query.source, query.cursor) == (20, None, None, None)


def test_parse_list_query_treats_blank_optional_parameters_as_absent() -> None:
    query = parse_list_query(
        {"lang": "en", "limit": "", "category": "", "source": "", "cursor": ""}, LIMITS
    )

    assert (query.limit, query.category, query.source, query.cursor) == (20, None, None, None)


@pytest.mark.parametrize("limit", ["1", "100"])
def test_parse_list_query_accepts_limits_at_the_bounds(limit: str) -> None:
    assert parse_list_query({"lang": "en", "limit": limit}, LIMITS).limit == int(limit)


@pytest.mark.parametrize(
    ("args", "expected_code"),
    [
        pytest.param({}, "invalid_language", id="language missing"),
        pytest.param({"lang": "fr"}, "invalid_language", id="language unsupported"),
        pytest.param({"lang": "EN"}, "invalid_language", id="language uppercase"),
        pytest.param({"lang": "en", "limit": "abc"}, "invalid_limit", id="limit not a number"),
        pytest.param({"lang": "en", "limit": "2.5"}, "invalid_limit", id="limit fractional"),
        pytest.param({"lang": "en", "limit": "0"}, "invalid_limit", id="limit below one"),
        pytest.param({"lang": "en", "limit": "101"}, "invalid_limit", id="limit above maximum"),
        pytest.param({"lang": "en", "cursor": "garbage"}, "invalid_cursor", id="cursor malformed"),
    ],
)
def test_parse_list_query_rejects_invalid_parameters(args: dict[str, str], expected_code: str) -> None:
    with pytest.raises(InvalidRequestError) as raised:
        parse_list_query(args, LIMITS)

    assert raised.value.code == expected_code


@pytest.mark.parametrize("lang", [Language.ENGLISH, Language.VIETNAMESE])
def test_parse_detail_query_reads_the_language(lang: Language) -> None:
    assert parse_detail_query({"lang": lang.value}).lang is lang


@pytest.mark.parametrize("args", [{}, {"lang": "fr"}], ids=["language missing", "language unsupported"])
def test_parse_detail_query_rejects_an_invalid_language(args: dict[str, str]) -> None:
    with pytest.raises(InvalidRequestError) as raised:
        parse_detail_query(args)

    assert raised.value.code == "invalid_language"
