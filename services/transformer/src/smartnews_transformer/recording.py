from smartnews_common.db.transformations import TransformationStore
from smartnews_common.models import Transformation
from sqlalchemy import Engine


class DatabaseTransformationRecorder:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, article_id: int, transformation: Transformation) -> None:
        with self._engine.begin() as connection:
            TransformationStore(connection).upsert(article_id, transformation)

    def record_content(self, article_id: int, content: str) -> None:
        with self._engine.begin() as connection:
            TransformationStore(connection).upsert_content(article_id, content)
