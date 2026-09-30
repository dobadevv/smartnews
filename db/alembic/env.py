from alembic import context
from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env


def _database_url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or require_env(
        "DATABASE_URL"
    )


def run_migrations_online() -> None:
    engine = create_database_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported; run against a database")
run_migrations_online()
