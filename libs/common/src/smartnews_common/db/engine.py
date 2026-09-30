from sqlalchemy import Engine, create_engine

_PSYCOPG_SCHEME = "postgresql+psycopg://"
_PLAIN_SCHEMES = ("postgresql://", "postgres://")


def create_database_engine(database_url: str) -> Engine:
    # pool_pre_ping replaces a dropped connection transparently, which is
    # what the old PostgresSeenStore reconnect logic did by hand.
    return create_engine(_with_psycopg_driver(database_url), pool_pre_ping=True)


def _with_psycopg_driver(database_url: str) -> str:
    for plain_scheme in _PLAIN_SCHEMES:
        if database_url.startswith(plain_scheme):
            return _PSYCOPG_SCHEME + database_url.removeprefix(plain_scheme)
    return database_url
