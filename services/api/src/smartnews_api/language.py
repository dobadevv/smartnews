from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class Language(StrEnum):
    ENGLISH = "en"
    VIETNAMESE = "vi"


class CatalogRow(Protocol):
    """An `article_catalog` row as returned by the list query.

    Members are read-only properties so that sqlc rows, whose columns may be
    narrower (`str` rather than `str | None`), still satisfy the protocol.
    """

    @property
    def id(self) -> int: ...
    @property
    def title_en(self) -> str | None: ...
    @property
    def title_vi(self) -> str | None: ...
    @property
    def summary_en(self) -> str | None: ...
    @property
    def summary_vi(self) -> str | None: ...
    @property
    def thumbnail(self) -> str | None: ...
    @property
    def published_at(self) -> datetime | None: ...
    @property
    def url(self) -> str: ...
    @property
    def source(self) -> str: ...
    @property
    def category(self) -> str | None: ...
    @property
    def sort_at(self) -> datetime: ...


class CatalogDetailRow(CatalogRow, Protocol):
    @property
    def content_en(self) -> str | None: ...
    @property
    def content_vi(self) -> str | None: ...


@dataclass(frozen=True)
class LocalizedArticle:
    id: int
    title: str
    summary: str
    thumbnail: str
    published_at: datetime | None
    sort_at: datetime | None
    url: str
    source: str
    category: str | None


@dataclass(frozen=True)
class LocalizedArticleDetail(LocalizedArticle):
    content: str


def localize_article(row: CatalogRow, language: Language) -> LocalizedArticle:
    title, summary = _title_and_summary(row, language)
    return LocalizedArticle(
        id=row.id,
        title=title,
        summary=summary,
        thumbnail=_required(row.thumbnail, "thumbnail"),
        published_at=row.published_at,
        url=row.url,
        source=row.source,
        category=row.category,
        sort_at=row.sort_at,
    )


def localize_article_detail(row: CatalogDetailRow, language: Language) -> LocalizedArticleDetail:
    content = row.content_en if language is Language.ENGLISH else row.content_vi
    return LocalizedArticleDetail(
        **asdict(localize_article(row, language)), content=_required(content, "content")
    )


def _title_and_summary(row: CatalogRow, language: Language) -> tuple[str, str]:
    if language is Language.ENGLISH:
        title, summary = row.title_en, row.summary_en
    else:
        title, summary = row.title_vi, row.summary_vi
    return _required(title, "title"), _required(summary, "summary")


def _required[T](value: T | None, field: str) -> T:
    # The catalog queries only return rows whose fields for the requested
    # language are non-null; a None here means a query broke that contract.
    if value is None:
        raise ValueError(f"catalog row has no {field} for the requested language")
    return value
