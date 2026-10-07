from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from smartnews_common.db.catalog import ArticleCatalogStore, CatalogPageQuery
from sqlalchemy import Engine

JANUARY_1 = datetime(2026, 1, 1, tzinfo=UTC)
JANUARY_2 = datetime(2026, 1, 2, tzinfo=UTC)
JANUARY_3 = datetime(2026, 1, 3, tzinfo=UTC)
INDOCHINA = timezone(timedelta(hours=7))


def list_rows(engine: Engine, query: CatalogPageQuery) -> list:
    with engine.connect() as connection:
        return ArticleCatalogStore(connection).list_page(query)


def list_ids(engine: Engine, query: CatalogPageQuery) -> list[int]:
    return [row.id for row in list_rows(engine, query)]


def get_article(engine: Engine, article_id: int, language: str):
    with engine.connect() as connection:
        return ArticleCatalogStore(connection).get(article_id, language)


@pytest.mark.parametrize(
    ("language", "missing_field"),
    [
        ("en", "summary_en"),
        ("en", "content_en"),
        ("en", "thumbnail"),
        ("vi", "title_vi"),
        ("vi", "summary_vi"),
        ("vi", "content_vi"),
        ("vi", "thumbnail"),
    ],
)
def test_list_page_skips_articles_missing_a_listed_field_in_the_language(
    engine: Engine, insert_catalog_article: Callable[..., int], language: str, missing_field: str
) -> None:
    complete_id = insert_catalog_article()
    insert_catalog_article(**{missing_field: None})

    assert list_ids(engine, CatalogPageQuery(language=language, page_size=10)) == [complete_id]


@pytest.mark.parametrize(
    ("language", "other_language_content"), [("en", "content_vi"), ("vi", "content_en")]
)
def test_list_page_does_not_require_content_in_the_other_language(
    engine: Engine, insert_catalog_article: Callable[..., int], language: str, other_language_content: str
) -> None:
    article_id = insert_catalog_article(**{other_language_content: None})

    assert list_ids(engine, CatalogPageQuery(language=language, page_size=10)) == [article_id]


def test_list_page_lists_english_articles_that_have_no_translation(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    article_id = insert_catalog_article(title_vi=None, summary_vi=None, content_vi=None)

    assert list_ids(engine, CatalogPageQuery(language="en", page_size=10)) == [article_id]
    assert list_ids(engine, CatalogPageQuery(language="vi", page_size=10)) == []


@pytest.mark.parametrize(
    ("category", "source", "expected"),
    [
        (None, None, ["sports-vnexpress", "tech-hackernews", "tech-vnexpress"]),
        ("tech", None, ["tech-hackernews", "tech-vnexpress"]),
        (None, "vnexpress", ["sports-vnexpress", "tech-vnexpress"]),
        ("tech", "vnexpress", ["tech-vnexpress"]),
    ],
)
def test_list_page_applies_only_the_given_filters(
    engine: Engine,
    insert_catalog_article: Callable[..., int],
    category: str | None,
    source: str | None,
    expected: list[str],
) -> None:
    names_by_id = {
        insert_catalog_article(category="tech", source="vnexpress"): "tech-vnexpress",
        insert_catalog_article(category="tech", source="hackernews"): "tech-hackernews",
        insert_catalog_article(category="sports", source="vnexpress"): "sports-vnexpress",
    }
    query = CatalogPageQuery(language="en", page_size=10, category=category, source=source)

    assert [names_by_id[article_id] for article_id in list_ids(engine, query)] == expected


def test_list_page_orders_newest_first_and_breaks_ties_by_id(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    older = insert_catalog_article(published_at=JANUARY_1)
    newer_first = insert_catalog_article(published_at=JANUARY_2)
    newer_second = insert_catalog_article(published_at=JANUARY_2)

    assert list_ids(engine, CatalogPageQuery(language="en", page_size=10)) == [
        newer_second, newer_first, older
    ]


def test_list_page_orders_undated_articles_by_creation_time(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    dated = insert_catalog_article(published_at=JANUARY_2)
    undated = insert_catalog_article(published_at=None, created_at=JANUARY_3)

    assert list_ids(engine, CatalogPageQuery(language="en", page_size=10)) == [undated, dated]


def test_list_page_resumes_after_the_cursor_without_overlap(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    january_1_ids = [insert_catalog_article(published_at=JANUARY_1) for _ in range(3)]
    january_2_ids = [insert_catalog_article(published_at=JANUARY_2) for _ in range(2)]
    newest_first = list(reversed(january_1_ids + january_2_ids))

    first_page = list_rows(engine, CatalogPageQuery(language="en", page_size=3))
    last = first_page[-1]
    second_page = list_ids(
        engine,
        CatalogPageQuery(language="en", page_size=10, cursor_sort_at=last.sort_at, cursor_id=last.id),
    )

    assert [row.id for row in first_page] + second_page == newest_first


@pytest.mark.parametrize(
    ("language", "expected_content"), [("en", "Content"), ("vi", "Nội dung")]
)
def test_get_returns_the_article_when_complete_in_the_language(
    engine: Engine, insert_catalog_article: Callable[..., int], language: str, expected_content: str
) -> None:
    article_id = insert_catalog_article()

    row = get_article(engine, article_id, language)

    assert row is not None
    assert (row.id, getattr(row, f"content_{language}")) == (article_id, expected_content)


@pytest.mark.parametrize(
    ("language", "missing_field"),
    [
        ("en", "content_en"),
        ("en", "summary_en"),
        ("en", "thumbnail"),
        ("vi", "content_vi"),
        ("vi", "title_vi"),
        ("vi", "summary_vi"),
    ],
)
def test_get_returns_nothing_when_a_detail_field_is_missing(
    engine: Engine, insert_catalog_article: Callable[..., int], language: str, missing_field: str
) -> None:
    article_id = insert_catalog_article(**{missing_field: None})

    assert get_article(engine, article_id, language) is None


def test_get_returns_nothing_for_an_unknown_id(engine: Engine) -> None:
    assert get_article(engine, 999, "en") is None


@pytest.mark.parametrize(
    ("sort_at_from", "sort_at_to", "expected"),
    [
        pytest.param(JANUARY_2, None, ["january-3", "january-2"], id="from is inclusive"),
        pytest.param(None, JANUARY_2, ["january-1"], id="to is exclusive"),
        pytest.param(JANUARY_1, JANUARY_3, ["january-2", "january-1"], id="both bounds"),
        pytest.param(JANUARY_2, JANUARY_2, [], id="empty range"),
        pytest.param(
            datetime(2026, 1, 2, 7, tzinfo=INDOCHINA), None, ["january-3", "january-2"],
            id="from in another offset is inclusive at the same instant",
        ),
        pytest.param(
            None, datetime(2026, 1, 2, 7, tzinfo=INDOCHINA), ["january-1"],
            id="to in another offset is exclusive at the same instant",
        ),
    ],
)
def test_list_page_keeps_only_articles_inside_the_sort_at_range(
    engine: Engine,
    insert_catalog_article: Callable[..., int],
    sort_at_from: datetime | None,
    sort_at_to: datetime | None,
    expected: list[str],
) -> None:
    names_by_id = {
        insert_catalog_article(published_at=JANUARY_1): "january-1",
        insert_catalog_article(published_at=JANUARY_2): "january-2",
        insert_catalog_article(published_at=JANUARY_3): "january-3",
    }
    query = CatalogPageQuery(
        language="en", page_size=10, sort_at_from=sort_at_from, sort_at_to=sort_at_to
    )

    assert [names_by_id[article_id] for article_id in list_ids(engine, query)] == expected


@pytest.mark.parametrize(
    ("sort_at_from", "sort_at_to", "is_listed"),
    [
        pytest.param(JANUARY_2, None, True, id="created exactly at from"),
        pytest.param(None, JANUARY_2, False, id="created exactly at to"),
    ],
)
def test_list_page_bounds_undated_articles_by_creation_time(
    engine: Engine,
    insert_catalog_article: Callable[..., int],
    sort_at_from: datetime | None,
    sort_at_to: datetime | None,
    is_listed: bool,
) -> None:
    undated = insert_catalog_article(published_at=None, created_at=JANUARY_2)
    query = CatalogPageQuery(
        language="en", page_size=10, sort_at_from=sort_at_from, sort_at_to=sort_at_to
    )

    assert list_ids(engine, query) == ([undated] if is_listed else [])


def test_list_page_resumes_after_the_cursor_inside_the_sort_at_range(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    january_1 = insert_catalog_article(published_at=JANUARY_1)
    january_2_first = insert_catalog_article(published_at=JANUARY_2)
    january_2_second = insert_catalog_article(published_at=JANUARY_2)
    insert_catalog_article(published_at=JANUARY_3)
    in_range = CatalogPageQuery(
        language="en", page_size=2, sort_at_from=JANUARY_1, sort_at_to=JANUARY_3
    )

    first_page = list_rows(engine, in_range)
    last = first_page[-1]
    second_page = list_ids(
        engine,
        replace(in_range, page_size=10, cursor_sort_at=last.sort_at, cursor_id=last.id),
    )

    assert [row.id for row in first_page] == [january_2_second, january_2_first]
    assert second_page == [january_1]
