from datetime import UTC, datetime

from smartnews_common.db.articles import ArticleStore
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
