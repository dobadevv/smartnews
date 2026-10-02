import logging

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from smartnews_api.requests import InvalidRequestError

logger = logging.getLogger(__name__)


class ArticleNotFoundError(Exception):
    def __init__(self, article_id: int) -> None:
        super().__init__(f"article {article_id} not found")
        self.article_id = article_id


def register_error_handlers(app: Flask) -> None:
    app.register_error_handler(InvalidRequestError, _invalid_request)
    app.register_error_handler(ArticleNotFoundError, _article_not_found)
    app.register_error_handler(HTTPException, _http_error)
    app.register_error_handler(Exception, _unexpected_error)


def _invalid_request(error: InvalidRequestError) -> tuple[Response, int]:
    return _error_response(400, error.code, error.message)


def _article_not_found(error: ArticleNotFoundError) -> tuple[Response, int]:
    return _error_response(
        404,
        "article_not_found",
        f"article {error.article_id} does not exist or is not available in the requested language",
    )


def _http_error(error: HTTPException) -> tuple[Response, int]:
    # Werkzeug names ("Not Found", "Method Not Allowed") become "not_found", ...
    code = (error.name or "http_error").lower().replace(" ", "_")
    return _error_response(error.code or 500, code, error.description or code)


def _unexpected_error(error: Exception) -> tuple[Response, int]:
    logger.error("unhandled error serving %s %s", request.method, request.path, exc_info=error)
    return _error_response(500, "internal_error", "an unexpected error occurred")


def _error_response(status: int, code: str, message: str) -> tuple[Response, int]:
    return jsonify(error={"code": code, "message": message}), status
