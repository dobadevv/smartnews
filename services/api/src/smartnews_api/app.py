from dataclasses import dataclass

from flask import Flask
from flask_cors import CORS

from smartnews_api.errors import register_error_handlers
from smartnews_api.requests import PageSizeLimits
from smartnews_api.routes import (
    ArticleReader,
    ArticlesBlueprintDeps,
    build_articles_blueprint,
)


@dataclass(frozen=True)
class AppDeps:
    reader: ArticleReader
    page_size_limits: PageSizeLimits
    cors_allowed_origins: list[str]


def create_app(deps: AppDeps) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=deps.cors_allowed_origins, methods=["GET"])
    app.register_blueprint(
        build_articles_blueprint(
            ArticlesBlueprintDeps(reader=deps.reader, page_size_limits=deps.page_size_limits)
        )
    )
    register_error_handlers(app)
    return app
