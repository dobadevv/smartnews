from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine, text


def read_catalog_row(engine: Engine, article_id: int) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT * FROM article_catalog WHERE id = :id"), {"id": article_id}
            ).mappings().one()
        )


def test_article_catalog_exposes_both_languages_side_by_side(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    published_at = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
    article_id = insert_catalog_article(
        title_en="Title",
        summary_en="Summary",
        content_en="Content",
        title_vi="Tiêu đề",
        summary_vi="Tóm tắt",
        content_vi="Nội dung",
        thumbnail="https://example.com/t.png",
        published_at=published_at,
        source="vnexpress",
        category="tech",
    )

    row = read_catalog_row(engine, article_id)

    assert row == {
        "id": article_id,
        "title_en": "Title",
        "title_vi": "Tiêu đề",
        "summary_en": "Summary",
        "summary_vi": "Tóm tắt",
        "content_en": "Content",
        "content_vi": "Nội dung",
        "thumbnail": "https://example.com/t.png",
        "published_at": published_at,
        "url": row["url"],
        "source": "vnexpress",
        "category": "tech",
        "sort_at": published_at,
    }


def test_article_catalog_keeps_articles_without_translation_or_content(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    article_id = insert_catalog_article(
        content_en=None, title_vi=None, summary_vi=None, content_vi=None
    )

    row = read_catalog_row(engine, article_id)

    assert (row["title_en"], row["title_vi"], row["summary_vi"], row["content_en"], row["content_vi"]) == (
        "Title", None, None, None, None
    )


def test_article_catalog_sorts_by_created_at_when_published_at_is_missing(
    engine: Engine, insert_catalog_article: Callable[..., int]
) -> None:
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    article_id = insert_catalog_article(published_at=None, created_at=created_at)

    row = read_catalog_row(engine, article_id)

    assert (row["published_at"], row["sort_at"]) == (None, created_at)
