import pytest
from smartnews_common.db.articles import ArticleStore
from smartnews_common.db.contents import ContentStore
from smartnews_common.models import Article
from sqlalchemy import Engine, text


@pytest.fixture
def article_id(engine: Engine) -> int:
    article = Article(
        title="Title", url="https://example.com/a", source="s", published_at=None, summary=None
    )
    with engine.begin() as connection:
        inserted_id = ArticleStore(connection).insert_if_absent(article)
    assert inserted_id is not None
    return inserted_id


def read_content(engine: Engine, article_id: int) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT content, extractor FROM article_contents WHERE article_id = :id"),
                {"id": article_id},
            ).mappings().one()
        )


def test_upsert_stores_the_content(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        ContentStore(connection).upsert(article_id, "Full text", "trafilatura")

    assert read_content(engine, article_id) == {"content": "Full text", "extractor": "trafilatura"}


def test_upsert_overwrites_existing_content(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        ContentStore(connection).upsert(article_id, "Old", "trafilatura")
    with engine.begin() as connection:
        ContentStore(connection).upsert(article_id, "New", "selector:some-source")

    assert read_content(engine, article_id) == {"content": "New", "extractor": "selector:some-source"}
