from sqlalchemy import Connection

from smartnews_common.db.generated import articles as queries
from smartnews_common.dedup import article_key
from smartnews_common.models import Article


class ArticleStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def insert_if_absent(self, article: Article) -> int | None:
        """Store the article and return its id, or None if its URL was already stored."""
        return self._querier.insert_article_if_absent(
            hash_url=article_key(article),
            url=article.url,
            title=article.title,
            summary=article.summary,
            published_at=article.published_at,
            source=article.source,
            thumbnail=article.thumbnail,
            category=article.category,
        )

    def list_untransformed(
        self, min_age_minutes: int, limit: int
    ) -> list[queries.ListUntransformedArticlesRow]:
        """Return up to `limit` articles at least `min_age_minutes` old whose
        title and summary were never translated, oldest first."""
        return list(
            self._querier.list_untransformed_articles(
                min_age_minutes=min_age_minutes, max_rows=limit
            )
        )
