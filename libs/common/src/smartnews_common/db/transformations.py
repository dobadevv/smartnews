from sqlalchemy import Connection

from smartnews_common.db.generated import transformations as queries
from smartnews_common.models import Transformation


class TransformationStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def upsert(self, article_id: int, transformation: Transformation) -> None:
        self._querier.upsert_article_transformation(
            article_id=article_id,
            title=transformation.title,
            summary=transformation.summary,
            language=transformation.language,
        )

    def upsert_content(self, article_id: int, content: str) -> None:
        self._querier.upsert_article_transformation_content(
            article_id=article_id, content=content
        )
