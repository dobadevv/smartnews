import psycopg


class PostgresSeenStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def ensure_schema(self) -> None:
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_articles (
                    key TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (key, channel)
                )
                """
            )

    def filter_unseen(self, keys: list[str], channel: str) -> set[str]:
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            seen = conn.execute(
                "SELECT key FROM seen_articles WHERE channel = %s AND key = ANY(%s)",
                (channel, keys),
            ).fetchall()
        seen_keys = {row[0] for row in seen}
        return set(keys) - seen_keys

    def mark_seen(self, key: str, channel: str) -> None:
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute(
                "INSERT INTO seen_articles (key, channel) VALUES (%s, %s) "
                "ON CONFLICT (key, channel) DO NOTHING",
                (key, channel),
            )
