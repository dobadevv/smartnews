from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

import pytest
from flask.testing import FlaskClient
from smartnews_api.app import create_app
from smartnews_api.catalog import ArticlePage
from smartnews_api.facets import Facet
from smartnews_api.language import Language, LocalizedArticle, LocalizedArticleDetail
from smartnews_api.requests import FacetQuery, ListArticlesQuery, PageSizeLimits

ALLOWED_ORIGIN = "https://reader.example"
INDOCHINA = timezone(timedelta(hours=7))

ARTICLE = LocalizedArticle(
    id=7,
    title="Tiêu đề",
    summary="Tóm tắt",
    thumbnail="https://example.com/t.png",
    published_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    sort_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    url="https://example.com/a",
    source="vnexpress",
    category="tech",
)
ARTICLE_JSON = {
    "id": 7,
    "title": "Tiêu đề",
    "summary": "Tóm tắt",
    "thumbnail": "https://example.com/t.png",
    "published_at": "2026-01-02T03:04:05+00:00",
    "sort_at": "2026-01-02T03:04:05+00:00",
    "url": "https://example.com/a",
    "source": "vnexpress",
    "category": "tech",
}


@dataclass
class FakeArticleReader:
    page: ArticlePage = field(default_factory=lambda: ArticlePage(items=[], next_cursor=None))
    detail: LocalizedArticleDetail | None = None
    facets: list[Facet] = field(default_factory=list)
    failure: Exception | None = None
    list_queries: list[ListArticlesQuery] = field(default_factory=list)
    detail_requests: list[tuple[int, Language]] = field(default_factory=list)
    facet_requests: list[tuple[str, FacetQuery]] = field(default_factory=list)

    def list_page(self, query: ListArticlesQuery) -> ArticlePage:
        self.list_queries.append(query)
        self._raise_failure()
        return self.page

    def get(self, article_id: int, language: Language) -> LocalizedArticleDetail | None:
        self.detail_requests.append((article_id, language))
        self._raise_failure()
        return self.detail

    def list_categories(self, query: FacetQuery) -> list[Facet]:
        self.facet_requests.append(("categories", query))
        self._raise_failure()
        return self.facets

    def list_sources(self, query: FacetQuery) -> list[Facet]:
        self.facet_requests.append(("sources", query))
        self._raise_failure()
        return self.facets

    def _raise_failure(self) -> None:
        if self.failure is not None:
            raise self.failure


@pytest.fixture
def reader() -> FakeArticleReader:
    return FakeArticleReader()


@pytest.fixture
def client(reader: FakeArticleReader) -> FlaskClient:
    app = create_app(
        reader=reader,
        page_size_limits=PageSizeLimits(default=20, maximum=100),
        cors_allowed_origins=[ALLOWED_ORIGIN],
    )
    return app.test_client()


def test_list_articles_returns_localized_items_and_the_next_cursor(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    reader.page = ArticlePage(items=[ARTICLE], next_cursor="next-token")

    response = client.get("/articles?lang=vi")

    assert response.status_code == 200
    assert response.get_json() == {"items": [ARTICLE_JSON], "next_cursor": "next-token"}


def test_list_articles_passes_the_parsed_parameters_to_the_reader(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    client.get("/articles?lang=en&limit=5&category=tech&source=vnexpress")

    [query] = reader.list_queries
    assert (query.lang, query.limit, query.category, query.source, query.cursor) == (
        Language.ENGLISH, 5, "tech", "vnexpress", None
    )


def test_list_articles_passes_the_parsed_sort_at_bounds_to_the_reader(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    client.get(
        "/articles?lang=en&sort_at_from=2026-10-01T00:00:00%2B07:00&sort_at_to=2026-10-08T00:00:00Z"
    )

    [query] = reader.list_queries
    assert (query.sort_at_from, query.sort_at_to) == (
        datetime(2026, 10, 1, tzinfo=INDOCHINA), datetime(2026, 10, 8, tzinfo=UTC)
    )


def test_list_articles_returns_an_empty_page_when_nothing_matches(client: FlaskClient) -> None:
    response = client.get("/articles?lang=en")

    assert (response.status_code, response.get_json()) == (200, {"items": [], "next_cursor": None})


def test_list_articles_serializes_a_missing_published_at_as_null(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    undated = LocalizedArticle(**{**ARTICLE.__dict__, "published_at": None})
    reader.page = ArticlePage(items=[undated], next_cursor=None)

    response = client.get("/articles?lang=vi")

    assert response.get_json()["items"][0]["published_at"] is None


def test_get_article_returns_the_localized_detail(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    reader.detail = LocalizedArticleDetail(**ARTICLE.__dict__, content="Nội dung")

    response = client.get("/articles/7?lang=vi")

    assert response.status_code == 200
    assert response.get_json() == {**ARTICLE_JSON, "content": "Nội dung"}
    assert reader.detail_requests == [(7, Language.VIETNAMESE)]


FACET_PATHS = [pytest.param("categories", id="categories"), pytest.param("sources", id="sources")]


@pytest.mark.parametrize("path", FACET_PATHS)
def test_facets_return_the_reader_items_without_a_cursor(
    client: FlaskClient, reader: FakeArticleReader, path: str
) -> None:
    reader.facets = [
        Facet(value="ai", label="AI", article_count=12),
        Facet(value="architecture", label="Architecture", article_count=0),
    ]

    response = client.get(f"/{path}?lang=vi")

    assert response.status_code == 200
    assert response.get_json() == {
        "items": [
            {"value": "ai", "label": "AI", "article_count": 12},
            {"value": "architecture", "label": "Architecture", "article_count": 0},
        ]
    }


@pytest.mark.parametrize("path", FACET_PATHS)
def test_facets_pass_the_parsed_query_to_the_reader(
    client: FlaskClient, reader: FakeArticleReader, path: str
) -> None:
    client.get(f"/{path}?lang=vi&sort_at_from=2026-10-01T00:00:00%2B07:00&sort_at_to=2026-10-08T00:00:00Z")

    assert reader.facet_requests == [
        (
            path,
            FacetQuery(lang=Language.VIETNAMESE).model_copy(
                update={
                    "sort_at_from": datetime(2026, 10, 1, tzinfo=INDOCHINA),
                    "sort_at_to": datetime(2026, 10, 8, tzinfo=UTC),
                }
            ),
        )
    ]


@pytest.mark.parametrize("path", FACET_PATHS)
def test_facets_ignore_parameters_of_the_article_list(
    client: FlaskClient, reader: FakeArticleReader, path: str
) -> None:
    response = client.get(f"/{path}?lang=en&limit=abc&cursor=garbage&category=ai&source=x")

    assert response.status_code == 200
    assert reader.facet_requests == [(path, FacetQuery(lang=Language.ENGLISH))]


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        pytest.param("GET", "/articles", 400, "invalid_language", id="list without language"),
        pytest.param("GET", "/articles?lang=fr", 400, "invalid_language", id="list unsupported language"),
        pytest.param("GET", "/articles?lang=en&limit=0", 400, "invalid_limit", id="limit below one"),
        pytest.param("GET", "/articles?lang=en&limit=101", 400, "invalid_limit", id="limit above maximum"),
        pytest.param("GET", "/articles?lang=en&cursor=garbage", 400, "invalid_cursor", id="malformed cursor"),
        pytest.param(
            "GET", "/articles?lang=en&sort_at_from=yesterday", 400, "invalid_sort_at", id="list invalid sort_at"
        ),
        pytest.param(
            "GET", "/articles?lang=en&sort_at_from=2026-10-01T00:00:00+07:00", 400, "invalid_sort_at",
            id="list unencoded plus in sort_at",
        ),
        pytest.param(
            "GET", "/articles?lang=en&sort_at_from=2026-10-02T00:00:00Z&sort_at_to=2026-10-01T00:00:00Z",
            400, "invalid_sort_at", id="list sort_at_from after sort_at_to",
        ),
        pytest.param("GET", "/categories", 400, "invalid_language", id="categories without language"),
        pytest.param("GET", "/sources?lang=fr", 400, "invalid_language", id="sources unsupported language"),
        pytest.param(
            "GET", "/categories?lang=en&sort_at_to=2026-10-01T00:00:00", 400, "invalid_sort_at",
            id="categories naive sort_at",
        ),
        pytest.param(
            "GET", "/sources?lang=en&sort_at_from=2026-10-01T00:00:00+07:00", 400, "invalid_sort_at",
            id="sources unencoded plus in sort_at",
        ),
        pytest.param(
            "GET", "/categories?sort_at_from=yesterday", 400, "invalid_language",
            id="categories language reported before sort_at",
        ),
        pytest.param("POST", "/sources?lang=en", 405, "method_not_allowed", id="facets wrong method"),
        pytest.param("GET", "/articles/7", 400, "invalid_language", id="detail without language"),
        pytest.param("GET", "/articles/7?lang=en", 404, "article_not_found", id="detail not found"),
        pytest.param("GET", "/articles/abc?lang=en", 404, "not_found", id="detail non-numeric id"),
        pytest.param("GET", "/unknown", 404, "not_found", id="unknown route"),
        pytest.param("POST", "/articles?lang=en", 405, "method_not_allowed", id="wrong method"),
    ],
)
def test_errors_use_the_shared_error_body(
    client: FlaskClient, method: str, path: str, status: int, code: str
) -> None:
    response = client.open(path, method=method)

    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code
    assert isinstance(response.get_json()["error"]["message"], str)


def test_unexpected_errors_return_500_without_internal_details(
    client: FlaskClient, reader: FakeArticleReader
) -> None:
    reader.failure = RuntimeError("connection to db-password-hunter2 failed")

    response = client.get("/articles?lang=en")

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("origin", "expected_header"),
    [(ALLOWED_ORIGIN, ALLOWED_ORIGIN), ("https://evil.example", None)],
    ids=["allowed origin", "other origin"],
)
def test_cors_allows_only_the_configured_origins(
    client: FlaskClient, origin: str, expected_header: str | None
) -> None:
    response = client.get("/articles?lang=en", headers={"Origin": origin})

    assert response.headers.get("Access-Control-Allow-Origin") == expected_header
