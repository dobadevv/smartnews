from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from smartnews_api.cursor import PageCursor, decode_cursor
from smartnews_api.language import Language


class InvalidRequestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PageSizeLimits:
    default: int
    maximum: int


def _parse_cursor(value: object) -> object:
    return decode_cursor(value) if isinstance(value, str) else value


def _parse_sort_at(value: object) -> datetime:
    # Query args are always strings. Rejecting anything else stops Pydantic's lax
    # coercion from reading a number as a Unix timestamp.
    if not isinstance(value, str):
        # Pydantic only turns ValueError into a validation error, so TypeError is no option.
        raise ValueError("sort_at bounds must be ISO-8601 strings")  # noqa: TRY004
    parsed = datetime.fromisoformat(value)
    # A naive time would be read in the database session's time zone.
    if parsed.tzinfo is None:
        raise ValueError("sort_at bounds must carry a UTC offset")
    return parsed


SortAt = Annotated[datetime | None, BeforeValidator(_parse_sort_at)]


def _ensure_sort_at_order(sort_at_to: datetime | None, info: ValidationInfo) -> datetime | None:
    # sort_at_from is absent from info.data when it failed validation; its own
    # error is then the one reported.
    sort_at_from = info.data.get("sort_at_from")
    if sort_at_to is not None and sort_at_from is not None and sort_at_to < sort_at_from:
        raise ValueError("sort_at_to must not be before sort_at_from")
    return sort_at_to


class ListArticlesQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: Language
    limit: int = Field(ge=1)
    category: str | None = None
    source: str | None = None
    cursor: Annotated[PageCursor | None, BeforeValidator(_parse_cursor)] = None
    sort_at_from: SortAt = None
    sort_at_to: SortAt = None

    @field_validator("limit")
    @classmethod
    def _limit_within_maximum(cls, limit: int, info: ValidationInfo) -> int:
        if info.context is None:
            raise TypeError("ListArticlesQuery must be validated with a max_page_size context")
        maximum = info.context["max_page_size"]
        if limit > maximum:
            raise ValueError(f"limit must be at most {maximum}")
        return limit

    @field_validator("sort_at_to")
    @classmethod
    def _sort_at_to_not_before_from(
        cls, sort_at_to: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        return _ensure_sort_at_order(sort_at_to, info)


class ArticleDetailQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: Language


class FacetQuery(BaseModel):
    # Not sharing a base model with ListArticlesQuery: Pydantic puts inherited
    # fields first, which would report time-bound errors before `lang`.
    model_config = ConfigDict(frozen=True)

    lang: Language
    sort_at_from: SortAt = None
    sort_at_to: SortAt = None

    @field_validator("sort_at_to")
    @classmethod
    def _sort_at_to_not_before_from(
        cls, sort_at_to: datetime | None, info: ValidationInfo
    ) -> datetime | None:
        return _ensure_sort_at_order(sort_at_to, info)


_INVALID_LANGUAGE = InvalidRequestError(
    "invalid_language", "lang is required and must be one of: en, vi"
)
_INVALID_CURSOR = InvalidRequestError(
    "invalid_cursor", "cursor is malformed; pass the next_cursor of a previous page"
)

_INVALID_SORT_AT = InvalidRequestError(
    "invalid_sort_at",
    "sort_at_from and sort_at_to must be ISO-8601 datetimes with a UTC offset,"
    " and sort_at_from must not be after sort_at_to",
)


def parse_list_query(args: Mapping[str, str], limits: PageSizeLimits) -> ListArticlesQuery:
    errors_by_field = {
        "lang": _INVALID_LANGUAGE,
        "limit": InvalidRequestError(
            "invalid_limit", f"limit must be an integer between 1 and {limits.maximum}"
        ),
        "cursor": _INVALID_CURSOR,
        "sort_at_from": _INVALID_SORT_AT,
        "sort_at_to": _INVALID_SORT_AT,
    }
    try:
        return ListArticlesQuery.model_validate(
            {"limit": limits.default, **_without_blank_values(args)},
            context={"max_page_size": limits.maximum},
        )
    except ValidationError as error:
        raise _first_invalid_field(error, errors_by_field) from error


def parse_detail_query(args: Mapping[str, str]) -> ArticleDetailQuery:
    try:
        return ArticleDetailQuery.model_validate(args)
    except ValidationError as error:
        raise _first_invalid_field(error, {"lang": _INVALID_LANGUAGE}) from error


def parse_facet_query(args: Mapping[str, str]) -> FacetQuery:
    errors_by_field = {
        "lang": _INVALID_LANGUAGE,
        "sort_at_from": _INVALID_SORT_AT,
        "sort_at_to": _INVALID_SORT_AT,
    }
    try:
        return FacetQuery.model_validate(_without_blank_values(args))
    except ValidationError as error:
        raise _first_invalid_field(error, errors_by_field) from error


def _without_blank_values(args: Mapping[str, str]) -> dict[str, str]:
    # Frontends send `?category=` or `?limit=` for an unset parameter; that means "not set".
    return {name: value for name, value in args.items() if value != ""}


def _first_invalid_field(
    error: ValidationError, errors_by_field: Mapping[str, InvalidRequestError]
) -> InvalidRequestError:
    # Pydantic's own messages name internals (enum and type names); clients get ours.
    field = error.errors()[0]["loc"][0]
    return errors_by_field[str(field)]
