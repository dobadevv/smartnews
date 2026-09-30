from sqlalchemy import Connection

from smartnews_common.db.generated import contents as queries


class ContentStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def upsert(self, article_id: int, content: str, extractor: str) -> None:
        self._querier.upsert_article_content(
            article_id=article_id, content=content, extractor=extractor
        )
