from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class Language(StrEnum):
    ENGLISH = "en"
    VIETNAMESE = "vi"


class CatalogRow(Protocol):
    """An `article_catalog` row as returned by the list query."""

    id: int
    title_en: str | None
    title_vi: str | None
    summary_en: str | None
    summary_vi: str | None
    thumbnail: str | None
    published_at: datetime | None
    url: str
    source: str
    category: str | None
    sort_at: datetime


class CatalogDetailRow(CatalogRow, Protocol):
    content_en: str | None
    content_vi: str | None


@dataclass(frozen=True)
class LocalizedArticle:
    id: int
    title: str
    summary: str
    thumbnail: str
    published_at: datetime | None
    url: str
    source: str
    category: str | None


@dataclass(frozen=True)
class LocalizedArticleDetail(LocalizedArticle):
    content: str


# The catalog queries only return rows whose fields for the requested language
# are non-null, so the localized fields below are never None.
def localize_article(row: CatalogRow, language: Language) -> LocalizedArticle:
    title, summary = _title_and_summary(row, language)
    return LocalizedArticle(
        id=row.id,
        title=title,
        summary=summary,
        thumbnail=row.thumbnail,
        published_at=row.published_at,
        url=row.url,
        source=row.source,
        category=row.category,
    )


def localize_article_detail(row: CatalogDetailRow, language: Language) -> LocalizedArticleDetail:
    content = row.content_en if language is Language.ENGLISH else row.content_vi
    return LocalizedArticleDetail(**asdict(localize_article(row, language)), content=content)


def _title_and_summary(row: CatalogRow, language: Language) -> tuple[str, str]:
    if language is Language.ENGLISH:
        return row.title_en, row.summary_en
    return row.title_vi, row.summary_vi
