from dataclasses import asdict
from typing import Protocol

from flask import Blueprint, Response, jsonify, request

from smartnews_api.catalog import ArticlePage
from smartnews_api.errors import ArticleNotFoundError
from smartnews_api.facets import Facet
from smartnews_api.language import Language, LocalizedArticle, LocalizedArticleDetail
from smartnews_api.requests import (
    FacetQuery,
    ListArticlesQuery,
    PageSizeLimits,
    parse_detail_query,
    parse_facet_query,
    parse_list_query,
)


class ArticleReader(Protocol):
    def list_page(self, query: ListArticlesQuery) -> ArticlePage: ...

    def get(self, article_id: int, language: Language) -> LocalizedArticleDetail | None: ...

    def list_categories(self, query: FacetQuery) -> list[Facet]: ...

    def list_sources(self, query: FacetQuery) -> list[Facet]: ...


def build_articles_blueprint(
    reader: ArticleReader, page_size_limits: PageSizeLimits
) -> Blueprint:
    blueprint = Blueprint("articles", __name__)

    @blueprint.get("/articles")
    def list_articles() -> Response:
        query = parse_list_query(request.args.to_dict(), page_size_limits)
        page = reader.list_page(query)
        return jsonify(
            items=[_article_json(article) for article in page.items],
            next_cursor=page.next_cursor,
        )

    @blueprint.get("/articles/<int:article_id>")
    def get_article(article_id: int) -> Response:
        query = parse_detail_query(request.args.to_dict())
        article = reader.get(article_id, query.lang)
        if article is None:
            raise ArticleNotFoundError(article_id)
        return jsonify(_article_json(article))

    @blueprint.get("/categories")
    def list_categories() -> Response:
        query = parse_facet_query(request.args.to_dict())
        return _facets_json(reader.list_categories(query))

    @blueprint.get("/sources")
    def list_sources() -> Response:
        query = parse_facet_query(request.args.to_dict())
        return _facets_json(reader.list_sources(query))

    return blueprint


def _facets_json(facets: list[Facet]) -> Response:
    return jsonify(items=[asdict(facet) for facet in facets])


def _article_json(article: LocalizedArticle) -> dict[str, object]:
    fields = asdict(article)
    # Flask would render datetimes as RFC 822; the frontend expects ISO-8601.
    fields["published_at"] = article.published_at.isoformat() if article.published_at else None
    fields["sort_at"] = article.sort_at.isoformat() if article.sort_at else None
    return fields
