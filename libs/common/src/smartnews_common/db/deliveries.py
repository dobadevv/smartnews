from sqlalchemy import Connection

from smartnews_common.db.generated import deliveries as queries


class DeliveryStore:
    def __init__(self, connection: Connection) -> None:
        self._querier = queries.Querier(connection)

    def is_delivered(self, article_id: int, channel: str) -> bool:
        return bool(self._querier.is_delivered(article_id=article_id, channel=channel))

    def mark_delivered(self, article_id: int, channel: str) -> None:
        self._querier.mark_delivered(article_id=article_id, channel=channel)
