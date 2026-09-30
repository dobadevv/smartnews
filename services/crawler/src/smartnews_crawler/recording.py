from smartnews_common.db.contents import ContentStore
from sqlalchemy import Engine


class DatabaseContentRecorder:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, article_id: int, content: str, extractor: str) -> None:
        with self._engine.begin() as connection:
            ContentStore(connection).upsert(article_id, content, extractor)
