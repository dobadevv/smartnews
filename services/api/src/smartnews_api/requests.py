from collections.abc import Mapping
from dataclasses import dataclass
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


class ListArticlesQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: Language
    limit: int = Field(ge=1)
    category: str | None = None
    source: str | None = None
    cursor: Annotated[PageCursor | None, BeforeValidator(_parse_cursor)] = None

    @field_validator("limit")
    @classmethod
    def _limit_within_maximum(cls, limit: int, info: ValidationInfo) -> int:
        if info.context is None:
            raise TypeError("ListArticlesQuery must be validated with a max_page_size context")
        maximum = info.context["max_page_size"]
        if limit > maximum:
            raise ValueError(f"limit must be at most {maximum}")
        return limit


class ArticleDetailQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    lang: Language


_INVALID_LANGUAGE = InvalidRequestError(
    "invalid_language", "lang is required and must be one of: en, vi"
)
_INVALID_CURSOR = InvalidRequestError(
    "invalid_cursor", "cursor is malformed; pass the next_cursor of a previous page"
)


def parse_list_query(args: Mapping[str, str], limits: PageSizeLimits) -> ListArticlesQuery:
    errors_by_field = {
        "lang": _INVALID_LANGUAGE,
        "limit": InvalidRequestError(
            "invalid_limit", f"limit must be an integer between 1 and {limits.maximum}"
        ),
        "cursor": _INVALID_CURSOR,
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


def _without_blank_values(args: Mapping[str, str]) -> dict[str, str]:
    # Frontends send `?category=` or `?limit=` for an unset parameter; that means "not set".
    return {name: value for name, value in args.items() if value != ""}


def _first_invalid_field(
    error: ValidationError, errors_by_field: Mapping[str, InvalidRequestError]
) -> InvalidRequestError:
    # Pydantic's own messages name internals (enum and type names); clients get ours.
    field = error.errors()[0]["loc"][0]
    return errors_by_field[str(field)]
