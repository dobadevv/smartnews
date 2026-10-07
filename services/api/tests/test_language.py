from datetime import UTC, datetime

import pytest
from smartnews_api.language import (
    Language,
    LocalizedArticle,
    LocalizedArticleDetail,
    localize_article,
    localize_article_detail,
)
from smartnews_common.db.generated.models import ArticleCatalog

PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def catalog_row() -> ArticleCatalog:
    return ArticleCatalog(
        id=7,
        title_en="Title",
        title_vi="Tiêu đề",
        summary_en="Summary",
        summary_vi="Tóm tắt",
        content_en="Content",
        content_vi="Nội dung",
        thumbnail="https://example.com/t.png",
        published_at=PUBLISHED_AT,
        url="https://example.com/a",
        source="vnexpress",
        category="tech",
        sort_at=PUBLISHED_AT,
    )


@pytest.mark.parametrize(
    ("language", "title", "summary"),
    [
        (Language.ENGLISH, "Title", "Summary"),
        (Language.VIETNAMESE, "Tiêu đề", "Tóm tắt"),
    ],
)
def test_localize_article_picks_the_texts_of_the_language(
    language: Language, title: str, summary: str
) -> None:
    assert localize_article(catalog_row(), language) == LocalizedArticle(
        id=7,
        title=title,
        summary=summary,
        thumbnail="https://example.com/t.png",
        published_at=PUBLISHED_AT,
        sort_at=PUBLISHED_AT,
        url="https://example.com/a",
        source="vnexpress",
        category="tech",
    )


@pytest.mark.parametrize(
    ("language", "title", "content"),
    [
        (Language.ENGLISH, "Title", "Content"),
        (Language.VIETNAMESE, "Tiêu đề", "Nội dung"),
    ],
)
def test_localize_article_detail_adds_the_content_of_the_language(
    language: Language, title: str, content: str
) -> None:
    detail = localize_article_detail(catalog_row(), language)

    assert isinstance(detail, LocalizedArticleDetail)
    assert (detail.title, detail.content) == (title, content)


def test_language_rejects_codes_other_than_lowercase_en_and_vi() -> None:
    with pytest.raises(ValueError):
        Language("EN")
