from dataclasses import asdict, dataclass
from typing import Protocol

from flask import Blueprint, Response, jsonify, request

from smartnews_api.catalog import ArticlePage
from smartnews_api.errors import ArticleNotFoundError
from smartnews_api.language import Language, LocalizedArticle, LocalizedArticleDetail
from smartnews_api.requests import (
    ListArticlesQuery,
    PageSizeLimits,
    parse_detail_query,
    parse_list_query,
)


class ArticleReader(Protocol):
    def list_page(self, query: ListArticlesQuery) -> ArticlePage: ...

    def get(self, article_id: int, language: Language) -> LocalizedArticleDetail | None: ...


@dataclass(frozen=True)
class ArticlesBlueprintDeps:
    reader: ArticleReader
    page_size_limits: PageSizeLimits


def build_articles_blueprint(deps: ArticlesBlueprintDeps) -> Blueprint:
    blueprint = Blueprint("articles", __name__)

    @blueprint.get("/articles")
    def list_articles() -> Response:
        query = parse_list_query(request.args.to_dict(), deps.page_size_limits)
        page = deps.reader.list_page(query)
        return jsonify(
            items=[_article_json(article) for article in page.items],
            next_cursor=page.next_cursor,
        )

    @blueprint.get("/articles/<int:article_id>")
    def get_article(article_id: int) -> Response:
        query = parse_detail_query(request.args.to_dict())
        article = deps.reader.get(article_id, query.lang)
        if article is None:
            raise ArticleNotFoundError(article_id)
        return jsonify(_article_json(article))

    return blueprint


def _article_json(article: LocalizedArticle) -> dict[str, object]:
    fields = asdict(article)
    # Flask would render datetimes as RFC 822; the frontend expects ISO-8601.
    fields["published_at"] = article.published_at.isoformat() if article.published_at else None
    return fields
