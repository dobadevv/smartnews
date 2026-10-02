from dataclasses import dataclass

from smartnews_common.db.catalog import (
    MAX_ARTICLE_ID,
    ArticleCatalogStore,
    CatalogPageQuery,
)
from sqlalchemy import Engine

from smartnews_api.cursor import PageCursor, encode_cursor
from smartnews_api.language import (
    CatalogRow,
    Language,
    LocalizedArticle,
    LocalizedArticleDetail,
    localize_article,
    localize_article_detail,
)
from smartnews_api.requests import ListArticlesQuery


@dataclass(frozen=True)
class ArticlePage:
    items: list[LocalizedArticle]
    next_cursor: str | None


class ArticleCatalogReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_page(self, query: ListArticlesQuery) -> ArticlePage:
        with self._engine.connect() as connection:
            rows = ArticleCatalogStore(connection).list_page(_catalog_page_query(query))
        # One extra row was requested: its presence means another page follows.
        page_rows = rows[: query.limit]
        has_next_page = len(rows) > query.limit
        return ArticlePage(
            items=[localize_article(row, query.lang) for row in page_rows],
            next_cursor=_cursor_after(page_rows[-1]) if has_next_page else None,
        )

    def get(self, article_id: int, language: Language) -> LocalizedArticleDetail | None:
        if article_id > MAX_ARTICLE_ID:
            return None
        with self._engine.connect() as connection:
            row = ArticleCatalogStore(connection).get(article_id, language.value)
        return localize_article_detail(row, language) if row is not None else None


def _catalog_page_query(query: ListArticlesQuery) -> CatalogPageQuery:
    cursor = query.cursor
    return CatalogPageQuery(
        language=query.lang.value,
        page_size=query.limit + 1,
        category=query.category,
        source=query.source,
        cursor_sort_at=cursor.sort_at if cursor else None,
        cursor_id=cursor.article_id if cursor else None,
    )


def _cursor_after(row: CatalogRow) -> str:
    return encode_cursor(PageCursor(sort_at=row.sort_at, article_id=row.id))
