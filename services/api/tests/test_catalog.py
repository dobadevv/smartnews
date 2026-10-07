from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from smartnews_api.catalog import ArticleCatalogReader
from smartnews_api.facets import CATEGORY_LABELS, SOURCE_LABELS
from smartnews_api.language import Language
from smartnews_api.requests import (
    ListArticlesQuery,
    PageSizeLimits,
    parse_facet_query,
    parse_list_query,
)
from sqlalchemy import Engine

LIMITS = PageSizeLimits(default=20, maximum=100)


def list_query(**args: str | None) -> ListArticlesQuery:
    present_args = {name: value for name, value in args.items() if value is not None}
    return parse_list_query({"lang": "en", **present_args}, LIMITS)


@pytest.fixture
def reader(engine: Engine) -> ArticleCatalogReader:
    return ArticleCatalogReader(engine)


def test_list_page_links_pages_until_the_last_one(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    oldest, middle, newest = (insert_catalog_article() for _ in range(3))

    first_page = reader.list_page(list_query(limit="2"))
    assert first_page.next_cursor is not None
    second_page = reader.list_page(list_query(limit="2", cursor=first_page.next_cursor))

    assert [article.id for article in first_page.items] == [newest, middle]
    assert [article.id for article in second_page.items] == [oldest]
    assert second_page.next_cursor is None


def test_list_page_has_no_next_cursor_when_the_last_page_is_exactly_full(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article()
    insert_catalog_article()

    page = reader.list_page(list_query(limit="2"))

    assert (len(page.items), page.next_cursor) == (2, None)


def test_list_page_continues_past_articles_without_published_at(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    dated = insert_catalog_article(published_at=datetime(2026, 1, 2, tzinfo=UTC))
    undated = insert_catalog_article(published_at=None, created_at=datetime(2026, 1, 3, tzinfo=UTC))

    first_page = reader.list_page(list_query(limit="1"))
    second_page = reader.list_page(list_query(limit="1", cursor=first_page.next_cursor))

    assert [article.id for article in first_page.items + second_page.items] == [undated, dated]


def test_list_page_returns_items_in_the_requested_language(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article(title_vi="Tiêu đề", summary_vi="Tóm tắt")

    [article] = reader.list_page(list_query(lang="vi")).items

    assert (article.title, article.summary) == ("Tiêu đề", "Tóm tắt")


def test_get_returns_the_localized_detail(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    article_id = insert_catalog_article(content_vi="Nội dung")

    detail = reader.get(article_id, Language.VIETNAMESE)

    assert detail is not None
    assert (detail.id, detail.content) == (article_id, "Nội dung")


def test_get_returns_nothing_when_the_article_lacks_content_in_the_language(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    article_id = insert_catalog_article(content_en=None)

    assert reader.get(article_id, Language.ENGLISH) is None


def test_get_returns_nothing_for_an_id_beyond_the_database_range(reader: ArticleCatalogReader) -> None:
    assert reader.get(2**63, Language.ENGLISH) is None


def test_list_page_keeps_only_articles_inside_the_sort_at_range(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article(published_at=datetime(2026, 1, 1, tzinfo=UTC))
    inside = insert_catalog_article(published_at=datetime(2026, 1, 2, tzinfo=UTC))
    insert_catalog_article(published_at=datetime(2026, 1, 3, tzinfo=UTC))

    page = reader.list_page(
        list_query(sort_at_from="2026-01-02T00:00:00Z", sort_at_to="2026-01-03T00:00:00Z")
    )

    assert [article.id for article in page.items] == [inside]


def test_list_categories_returns_every_labeled_category_sorted_with_its_count(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article(category="world")
    insert_catalog_article(category="ai")
    insert_catalog_article(category="ai")
    insert_catalog_article(category="not-a-configured-category")

    facets = reader.list_categories(parse_facet_query({"lang": "en"}))

    assert [facet.value for facet in facets] == sorted(CATEGORY_LABELS)
    assert {facet.value: facet.label for facet in facets} == dict(CATEGORY_LABELS)
    assert {facet.value: facet.article_count for facet in facets} == {
        **dict.fromkeys(CATEGORY_LABELS, 0), "ai": 2, "world": 1
    }


def test_list_sources_returns_every_labeled_source_sorted_with_its_count(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article(source="hacker-news")
    insert_catalog_article(source="hacker-news")
    insert_catalog_article(source="bbc-world")
    insert_catalog_article(source="not-a-configured-source")

    facets = reader.list_sources(parse_facet_query({"lang": "en"}))

    assert [facet.value for facet in facets] == sorted(SOURCE_LABELS)
    assert {facet.value: facet.label for facet in facets} == dict(SOURCE_LABELS)
    assert {facet.value: facet.article_count for facet in facets} == {
        **dict.fromkeys(SOURCE_LABELS, 0), "hacker-news": 2, "bbc-world": 1
    }


def test_list_categories_counts_only_the_requested_language_and_range(
    reader: ArticleCatalogReader, insert_catalog_article: Callable[..., int]
) -> None:
    insert_catalog_article(category="ai", published_at=datetime(2026, 1, 2, tzinfo=UTC))
    insert_catalog_article(category="ai", published_at=datetime(2026, 1, 1, tzinfo=UTC))
    insert_catalog_article(
        category="ai", published_at=datetime(2026, 1, 2, tzinfo=UTC), title_vi=None, summary_vi=None, content_vi=None
    )

    facets = reader.list_categories(
        parse_facet_query({"lang": "vi", "sort_at_from": "2026-01-02T00:00:00Z"})
    )

    assert {facet.value: facet.article_count for facet in facets}["ai"] == 1
