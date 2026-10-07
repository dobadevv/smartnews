from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import BaseModel, ValidationError
from smartnews_api.cursor import PageCursor, encode_cursor
from smartnews_api.language import Language
from smartnews_api.requests import (
    FacetQuery,
    InvalidRequestError,
    ListArticlesQuery,
    PageSizeLimits,
    parse_detail_query,
    parse_facet_query,
    parse_list_query,
)

LIMITS = PageSizeLimits(default=20, maximum=100)
CURSOR = PageCursor(sort_at=datetime(2026, 1, 1, tzinfo=UTC), article_id=5)
INDOCHINA = timezone(timedelta(hours=7))


def parse_list(args: dict[str, str]) -> ListArticlesQuery:
    return parse_list_query({"lang": "en", **args}, LIMITS)


def parse_facet(args: dict[str, str]) -> FacetQuery:
    return parse_facet_query({"lang": "en", **args})


Parser = Callable[[dict[str, str]], ListArticlesQuery | FacetQuery]

PARSERS = [pytest.param(parse_list, id="list"), pytest.param(parse_facet, id="facet")]


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


@pytest.mark.parametrize("parse", PARSERS)
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param("2026-10-01T00:00:00+07:00", datetime(2026, 10, 1, tzinfo=INDOCHINA), id="numeric offset"),
        pytest.param("2026-10-01T00:00:00Z", datetime(2026, 10, 1, tzinfo=UTC), id="zulu"),
    ],
)
def test_parsers_read_sort_at_bounds_with_an_offset(parse: Parser, raw: str, expected: datetime) -> None:
    query = parse({"sort_at_from": raw, "sort_at_to": raw})

    assert (query.sort_at_from, query.sort_at_to) == (expected, expected)
    assert query.sort_at_from is not None
    assert query.sort_at_from.utcoffset() == expected.utcoffset()


@pytest.mark.parametrize("parse", PARSERS)
@pytest.mark.parametrize(
    ("sort_at_from", "sort_at_to"),
    [
        pytest.param("2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z", id="equal bounds"),
        pytest.param("2026-10-01T08:00:00+07:00", "2026-10-01T01:30:00Z", id="later instant in an earlier wall clock"),
    ],
)
def test_parsers_accept_ordered_sort_at_bounds(parse: Parser, sort_at_from: str, sort_at_to: str) -> None:
    query = parse({"sort_at_from": sort_at_from, "sort_at_to": sort_at_to})

    assert query.sort_at_from is not None and query.sort_at_to is not None
    assert query.sort_at_from <= query.sort_at_to


@pytest.mark.parametrize("parse", PARSERS)
def test_parsers_treat_blank_sort_at_bounds_as_absent(parse: Parser) -> None:
    query = parse({"sort_at_from": "", "sort_at_to": ""})

    assert (query.sort_at_from, query.sort_at_to) == (None, None)


@pytest.mark.parametrize("parse", PARSERS)
@pytest.mark.parametrize(
    "args",
    [
        pytest.param({"sort_at_from": "yesterday"}, id="unparseable"),
        pytest.param({"sort_at_from": "2026-13-01T00:00:00Z"}, id="month out of range"),
        pytest.param({"sort_at_from": "2026-10-01T00:00:00"}, id="naive datetime"),
        pytest.param({"sort_at_to": "2026-10-01"}, id="date only"),
        pytest.param({"sort_at_from": "1700000000"}, id="unix timestamp"),
        pytest.param({"sort_at_from": "2026-10-01T00:00:00 07:00"}, id="unencoded plus arrived as space"),
        pytest.param(
            {"sort_at_from": "2026-10-02T00:00:00Z", "sort_at_to": "2026-10-01T00:00:00Z"}, id="from after to"
        ),
        pytest.param(
            {"sort_at_from": "2026-10-01T01:30:00Z", "sort_at_to": "2026-10-01T08:00:00+07:00"},
            id="earlier instant in a later wall clock",
        ),
        pytest.param({"sort_at_from": "garbage", "sort_at_to": "2026-10-01T00:00:00Z"}, id="invalid from valid to"),
        pytest.param({"sort_at_from": "2026-10-01T00:00:00Z", "sort_at_to": "garbage"}, id="valid from invalid to"),
    ],
)
def test_parsers_reject_invalid_sort_at_bounds(parse: Parser, args: dict[str, str]) -> None:
    with pytest.raises(InvalidRequestError) as raised:
        parse(args)

    assert raised.value.code == "invalid_sort_at"


@pytest.mark.parametrize("model", [ListArticlesQuery, FacetQuery])
def test_query_models_reject_a_non_string_sort_at_bound(model: type[BaseModel]) -> None:
    """Pydantic would coerce a number to a datetime; bounds must be ISO-8601 strings."""
    with pytest.raises(ValidationError):
        model.model_validate(
            {"lang": "en", "limit": 1, "sort_at_from": 1700000000},
            context={"max_page_size": 100},
        )


def test_parse_list_query_reports_the_limit_before_the_sort_at_bounds() -> None:
    with pytest.raises(InvalidRequestError) as raised:
        parse_list({"limit": "0", "sort_at_from": "yesterday"})

    assert raised.value.code == "invalid_limit"


@pytest.mark.parametrize("lang", [Language.ENGLISH, Language.VIETNAMESE])
def test_parse_facet_query_reads_the_language_and_defaults_the_bounds(lang: Language) -> None:
    query = parse_facet_query({"lang": lang.value})

    assert (query.lang, query.sort_at_from, query.sort_at_to) == (lang, None, None)


def test_parse_facet_query_ignores_parameters_of_the_article_list() -> None:
    query = parse_facet_query(
        {"lang": "en", "limit": "abc", "cursor": "garbage", "category": "ai", "source": "x", "page": "2"}
    )

    assert query == FacetQuery(lang=Language.ENGLISH)


@pytest.mark.parametrize(
    "args",
    [
        pytest.param({}, id="language missing"),
        pytest.param({"lang": ""}, id="language blank"),
        pytest.param({"lang": "fr"}, id="language unsupported"),
        pytest.param({"lang": "EN"}, id="language uppercase"),
        pytest.param({"lang": "fr", "sort_at_from": "yesterday"}, id="language reported before the bounds"),
    ],
)
def test_parse_facet_query_rejects_an_invalid_language(args: dict[str, str]) -> None:
    with pytest.raises(InvalidRequestError) as raised:
        parse_facet_query(args)

    assert raised.value.code == "invalid_language"
