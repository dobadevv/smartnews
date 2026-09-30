from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from smartnews_common.db.engine import create_database_engine
from sqlalchemy import Engine, text
from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parent
APPLICATION_TABLES = "article_deliveries, article_transformations, articles"


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url(driver=None)
        alembic_config = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_config.set_main_option("sqlalchemy.url", url)
        command.upgrade(alembic_config, "head")
        yield url


@pytest.fixture(scope="session")
def database_engine(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_database_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(database_engine: Engine) -> Engine:
    with database_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {APPLICATION_TABLES} RESTART IDENTITY"))
    return database_engine
