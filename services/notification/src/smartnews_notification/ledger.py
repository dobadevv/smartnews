from smartnews_common.db.deliveries import DeliveryStore
from sqlalchemy import Engine


class DatabaseDeliveryLedger:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_delivered(self, article_id: int, channel: str) -> bool:
        with self._engine.connect() as connection:
            return DeliveryStore(connection).is_delivered(article_id, channel)

    def mark_delivered(self, article_id: int, channel: str) -> None:
        with self._engine.begin() as connection:
            DeliveryStore(connection).mark_delivered(article_id, channel)
