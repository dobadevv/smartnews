from pathlib import Path

from flask import Flask
from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging

from smartnews_api.app import AppDeps, create_app
from smartnews_api.catalog import ArticleCatalogReader
from smartnews_api.config import load_api_config

DEFAULT_CONFIG_PATH = Path("config/api.yaml")


def build_app() -> Flask:
    """Application factory for gunicorn: `gunicorn 'smartnews_api.wsgi:build_app()'`."""
    configure_logging()
    config = load_api_config(DEFAULT_CONFIG_PATH)
    return create_app(
        AppDeps(
            reader=ArticleCatalogReader(create_database_engine(require_env("DATABASE_URL"))),
            page_size_limits=config.page_size_limits,
            cors_allowed_origins=config.cors_allowed_origins,
        )
    )
