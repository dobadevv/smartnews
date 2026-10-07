from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection

from smartnews_common.db.generated import catalog as queries
from smartnews_common.db.generated.models import ArticleCatalog

# articles.id is a BIGINT; larger ids cannot exist and would make Postgres raise.
MAX_ARTICLE_ID = 2**63 - 1


@dataclass(frozen=True)
class CatalogPageQuery:
    language: str
    page_size: int
    category: str | None = None
    source: str | None = None
    cursor_sort_at: datetime | None = None
    cursor_id: int | None = None
    sort_at_from: datetime | None = None
    sort_at_to: datetime | None = None


@dataclass(frozen=True)
class CatalogCountQuery:
    language: str
    sort_at_from: datetime | None = None
    sort_at_to: datetime | None = None


class ArticleCatalogStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def list_page(self, query: CatalogPageQuery) -> list[queries.ListCatalogArticlesRow]:
        """Return up to `page_size` articles complete in `language`, newest first,
        inside the optional half-open `sort_at` range, starting after the cursor
        when one is given."""
        return list(
            self._querier.list_catalog_articles(
                language=query.language,
                category=query.category,
                source=query.source,
                sort_at_from=query.sort_at_from,
                sort_at_to=query.sort_at_to,
                cursor_sort_at=query.cursor_sort_at,
                cursor_id=query.cursor_id,
                page_size=query.page_size,
            )
        )

    def count_by_category(self, query: CatalogCountQuery) -> dict[str, int]:
        """Return how many articles `list_page` would list per category, for the
        categories that have at least one."""
        rows = self._querier.count_catalog_articles_by_category(
            language=query.language,
            sort_at_from=query.sort_at_from,
            sort_at_to=query.sort_at_to,
        )
        # The query already excludes null categories; the check only narrows the type.
        return {row.category: row.article_count for row in rows if row.category is not None}

    def count_by_source(self, query: CatalogCountQuery) -> dict[str, int]:
        """Return how many articles `list_page` would list per source, for the
        sources that have at least one."""
        rows = self._querier.count_catalog_articles_by_source(
            language=query.language,
            sort_at_from=query.sort_at_from,
            sort_at_to=query.sort_at_to,
        )
        return {row.source: row.article_count for row in rows}

    def get(self, article_id: int, language: str) -> ArticleCatalog | None:
        """Return the article if it is complete, content included, in `language`."""
        return self._querier.get_catalog_article(article_id=article_id, language=language)
