from collections.abc import Iterator

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from smartnews.repository.postgres import PostgresSeenStore


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url(driver=None)


@pytest.fixture
def seen_store(postgres_dsn: str) -> Iterator[PostgresSeenStore]:
    with psycopg.connect(postgres_dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS seen_articles")

    store = PostgresSeenStore(postgres_dsn)
    store.ensure_schema()
    yield store
