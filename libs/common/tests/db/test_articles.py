from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from smartnews_common.db.articles import ArticleStore
from smartnews_common.db.generated.articles import ListUntransformedArticlesRow
from smartnews_common.dedup import article_key
from smartnews_common.models import Article
from sqlalchemy import Engine, text


def make_article(url: str = "https://example.com/a") -> Article:
    return Article(
        title="Title",
        url=url,
        source="example-blog",
        published_at=datetime(2026, 9, 30, 7, 0, tzinfo=UTC),
        summary="Summary",
        thumbnail="https://example.com/a.png",
        category="architecture",
    )


def test_insert_if_absent_returns_an_id_for_an_unseen_article(engine: Engine) -> None:
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(make_article())

    assert isinstance(article_id, int)


def test_insert_if_absent_returns_none_for_the_same_canonical_url(engine: Engine) -> None:
    with engine.begin() as connection:
        ArticleStore(connection).insert_if_absent(make_article("https://example.com/a"))
    with engine.begin() as connection:
        duplicate_id = ArticleStore(connection).insert_if_absent(
            make_article("https://example.com/a?utm_source=rss#top")
        )

    assert duplicate_id is None


def test_insert_if_absent_stores_every_article_field(engine: Engine) -> None:
    article = make_article()
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM articles WHERE id = :id"), {"id": article_id}
        ).mappings().one()

    assert row["hash_url"] == article_key(article)
    assert row["url"] == article.url
    assert row["title"] == article.title
    assert row["summary"] == article.summary
    assert row["published_at"] == article.published_at
    assert row["source"] == article.source
    assert row["thumbnail"] == article.thumbnail
    assert row["category"] == article.category


UNTRANSLATED = {"title_vi": None, "summary_vi": None, "content_vi": None}


def minutes_ago(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def list_untransformed(
    engine: Engine, min_age_minutes: int = 60, limit: int = 100
) -> list[ListUntransformedArticlesRow]:
    with engine.connect() as connection:
        return ArticleStore(connection).list_untransformed(
            min_age_minutes=min_age_minutes, limit=limit
        )


@pytest.mark.parametrize(
    ("translation", "expected_listed"),
    [
        pytest.param(UNTRANSLATED, True, id="no-transformation-row"),
        pytest.param(
            {"title_vi": None, "summary_vi": None, "content_vi": "Nội dung"},
            True,
            id="content-only-row",
        ),
        pytest.param(
            {"title_vi": "Tiêu đề", "summary_vi": "Tóm tắt", "content_vi": None},
            False,
            id="translated-title-and-summary",
        ),
        pytest.param(
            {"title_vi": "Tiêu đề", "summary_vi": None, "content_vi": None},
            False,
            id="translated-title-without-summary",
        ),
    ],
)
def test_list_untransformed_lists_only_articles_whose_title_and_summary_were_never_translated(
    engine: Engine,
    insert_catalog_article: Callable[..., int],
    translation: dict[str, str | None],
    expected_listed: bool,
) -> None:
    article_id = insert_catalog_article(created_at=minutes_ago(120), **translation)

    listed_ids = [row.id for row in list_untransformed(engine)]

    assert listed_ids == ([article_id] if expected_listed else [])


@pytest.mark.parametrize(
    ("age_minutes", "expected_listed"),
    [
        pytest.param(30, False, id="younger-than-the-minimum-age"),
        pytest.param(61, True, id="older-than-the-minimum-age"),
    ],
)
def test_list_untransformed_applies_the_minimum_age(
    engine: Engine,
    insert_catalog_article: Callable[..., int],
    age_minutes: int,
    expected_listed: bool,
) -> None:
    article_id = insert_catalog_article(
        created_at=minutes_ago(age_minutes), **UNTRANSLATED
    )

    listed_ids = [row.id for row in list_untransformed(engine, min_age_minutes=60)]

    assert listed_ids == ([article_id] if expected_listed else [])


def test_list_untransformed_with_no_minimum_age_lists_an_article_stored_just_now(
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(make_article())

    listed_ids = [row.id for row in list_untransformed(engine, min_age_minutes=0)]

    assert listed_ids == [article_id]


def test_list_untransformed_lists_the_oldest_first_and_stops_at_the_limit(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    oldest_created_at = minutes_ago(300)
    newest_id = insert_catalog_article(created_at=minutes_ago(180), **UNTRANSLATED)
    first_oldest_id = insert_catalog_article(created_at=oldest_created_at, **UNTRANSLATED)
    second_oldest_id = insert_catalog_article(created_at=oldest_created_at, **UNTRANSLATED)

    assert [row.id for row in list_untransformed(engine, limit=2)] == [
        first_oldest_id,
        second_oldest_id,
    ]
    assert [row.id for row in list_untransformed(engine, limit=3)] == [
        first_oldest_id,
        second_oldest_id,
        newest_id,
    ]


def test_list_untransformed_returns_the_stored_columns_an_article_fetched_message_needs(
    engine: Engine,
) -> None:
    article = make_article()
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)
    assert article_id is not None

    rows = list_untransformed(engine, min_age_minutes=0)

    assert rows == [
        ListUntransformedArticlesRow(
            id=article_id,
            hash_url=article_key(article),
            url=article.url,
            title=article.title,
            summary=article.summary,
            published_at=article.published_at,
            source=article.source,
            thumbnail=article.thumbnail,
            category=article.category,
        )
    ]
