from smartnews_common.db.articles import ArticleStore
from smartnews_common.models import Article
from smartnews_crawler.recording import DatabaseContentRecorder
from sqlalchemy import Engine, text


def test_record_persists_the_content(engine: Engine) -> None:
    article = Article(
        title="T", url="https://example.com/a", source="s", published_at=None, summary=None
    )
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)
    assert article_id is not None

    DatabaseContentRecorder(engine).record(article_id, "Full text", "trafilatura")

    with engine.connect() as connection:
        content = connection.execute(
            text("SELECT content FROM article_contents WHERE article_id = :id"),
            {"id": article_id},
        ).scalar_one()
    assert content == "Full text"
