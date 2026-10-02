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


class ArticleCatalogStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def list_page(self, query: CatalogPageQuery) -> list[queries.ListCatalogArticlesRow]:
        """Return up to `page_size` articles complete in `language`, newest first,
        starting after the cursor when one is given."""
        return list(
            self._querier.list_catalog_articles(
                language=query.language,
                category=query.category,
                source=query.source,
                cursor_sort_at=query.cursor_sort_at,
                cursor_id=query.cursor_id,
                page_size=query.page_size,
            )
        )

    def get(self, article_id: int, language: str) -> ArticleCatalog | None:
        """Return the article if it is complete, content included, in `language`."""
        return self._querier.get_catalog_article(article_id=article_id, language=language)
