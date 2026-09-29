import logging
from typing import Self

import psycopg

logger = logging.getLogger(__name__)


class PostgresSeenStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: psycopg.Connection | None = None

    def __enter__(self) -> Self:
        self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._conn is not None:
            self._conn.close()

    def ensure_schema(self) -> None:
        self._with_reconnect(
            lambda conn: conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_articles (
                    key TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (key, channel)
                )
                """
            )
        )

    def is_seen(self, key: str, channel: str) -> bool:
        def _query(conn: psycopg.Connection) -> bool:
            row = conn.execute(
                "SELECT 1 FROM seen_articles WHERE key = %s AND channel = %s",
                (key, channel),
            ).fetchone()
            return row is not None

        return self._with_reconnect(_query)

    def mark_seen(self, key: str, channel: str) -> None:
        self._with_reconnect(
            lambda conn: conn.execute(
                "INSERT INTO seen_articles (key, channel) VALUES (%s, %s) "
                "ON CONFLICT (key, channel) DO NOTHING",
                (key, channel),
            )
        )

    def _with_reconnect(self, operation):
        try:
            return operation(self._conn)
        except psycopg.OperationalError:
            logger.warning("postgres connection lost, reconnecting")
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            return operation(self._conn)
