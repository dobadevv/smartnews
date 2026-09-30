import pytest
from smartnews_common.db.engine import create_database_engine


@pytest.mark.parametrize(
    "database_url",
    [
        pytest.param("postgresql://u:p@localhost:5432/db", id="postgresql scheme"),
        pytest.param("postgres://u:p@localhost:5432/db", id="postgres scheme"),
        pytest.param("postgresql+psycopg://u:p@localhost:5432/db", id="explicit driver"),
    ],
)
def test_create_database_engine_uses_psycopg3_driver(database_url: str) -> None:
    engine = create_database_engine(database_url)

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.database == "db"
