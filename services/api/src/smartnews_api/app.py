from flask import Flask
from flask_cors import CORS

from smartnews_api.errors import register_error_handlers
from smartnews_api.requests import PageSizeLimits
from smartnews_api.routes import ArticleReader, build_articles_blueprint


def create_app(
    reader: ArticleReader,
    page_size_limits: PageSizeLimits,
    cors_allowed_origins: list[str],
) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=cors_allowed_origins, methods=["GET"])
    app.register_blueprint(
        build_articles_blueprint(reader=reader, page_size_limits=page_size_limits)
    )
    register_error_handlers(app)
    return app
