from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from smartnews_common.dedup import article_key
from smartnews_common.messages import ArticleCrawled, ArticleFetched, ArticleTransformed
from smartnews_common.models import Article, Transformation

ICT = timezone(timedelta(hours=7))


def make_article(published_at: datetime | None = datetime(2026, 9, 30, tzinfo=UTC)) -> Article:
    return Article(
        title="Hello",
        url="https://example.com/hello?utm_source=rss",
        source="example-blog",
        published_at=published_at,
        summary="Summary",
        thumbnail="https://example.com/hello.png",
        category="architecture",
    )


def test_from_article_carries_every_field_and_the_dedup_key() -> None:
    article = make_article()

    message = ArticleFetched.from_article(article, article_id=42)

    assert message.article_id == 42
    assert message.hash_url == article_key(article)
    assert message.to_article() == article


@pytest.mark.parametrize(
    "published_at",
    [
        pytest.param(datetime(2026, 9, 30, 14, 0, tzinfo=ICT), id="non-utc offset"),
        pytest.param(None, id="missing"),
    ],
)
def test_article_fetched_survives_a_json_round_trip(published_at: datetime | None) -> None:
    message = ArticleFetched.from_article(make_article(published_at), article_id=1)

    decoded = ArticleFetched.model_validate_json(message.model_dump_json())

    assert decoded == message
    assert decoded.published_at == published_at


def test_translated_replaces_title_and_summary_and_sets_language() -> None:
    fetched = ArticleFetched.from_article(make_article(), article_id=7)

    message = ArticleTransformed.translated(
        fetched, Transformation(title="Xin chào", summary="Tóm tắt", language="vi")
    )

    assert (message.title, message.summary, message.language) == ("Xin chào", "Tóm tắt", "vi")
    assert (message.article_id, message.url, message.hash_url) == (7, fetched.url, fetched.hash_url)


def test_untranslated_keeps_original_text_without_language() -> None:
    fetched = ArticleFetched.from_article(make_article(), article_id=7)

    message = ArticleTransformed.untranslated(fetched)

    assert message.to_article() == fetched.to_article()
    assert message.language is None


def test_messages_reject_an_unknown_schema_version() -> None:
    payload = ArticleFetched.from_article(make_article(), article_id=1).model_dump()
    payload["schema_version"] = 2

    with pytest.raises(ValidationError):
        ArticleFetched.model_validate(payload)


def test_from_fetched_carries_content_and_every_base_field() -> None:
    fetched = ArticleFetched.from_article(make_article(), article_id=7)

    message = ArticleCrawled.from_fetched(fetched, "Full article text")

    assert message.content == "Full article text"
    assert message.to_article() == fetched.to_article()
    assert (message.article_id, message.url, message.hash_url) == (7, fetched.url, fetched.hash_url)


def test_article_crawled_survives_a_json_round_trip() -> None:
    fetched = ArticleFetched.from_article(make_article(), article_id=1)
    message = ArticleCrawled.from_fetched(fetched, "Full text")

    decoded = ArticleCrawled.model_validate_json(message.model_dump_json())

    assert decoded == message
