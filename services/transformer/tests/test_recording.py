from smartnews_common.db.articles import ArticleStore
from smartnews_common.models import Article, Transformation
from smartnews_transformer.recording import DatabaseTransformationRecorder
from sqlalchemy import Engine, text


def test_record_persists_the_transformation(engine: Engine) -> None:
    article = Article(title="T", url="https://example.com/a", source="s", published_at=None, summary=None)
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)
    assert article_id is not None

    DatabaseTransformationRecorder(engine).record(
        article_id, Transformation(title="Tiêu đề", summary=None, language="vi")
    )

    with engine.connect() as connection:
        title = connection.execute(
            text("SELECT title FROM article_transformations WHERE article_id = :id"),
            {"id": article_id},
        ).scalar_one()
    assert title == "Tiêu đề"


def test_record_content_persists_the_content_without_a_title(engine: Engine) -> None:
    article = Article(title="T", url="https://example.com/b", source="s", published_at=None, summary=None)
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)
    assert article_id is not None

    DatabaseTransformationRecorder(engine).record_content(article_id, "Nội dung")

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT title, content FROM article_transformations WHERE article_id = :id"),
            {"id": article_id},
        ).one()
    assert tuple(row) == (None, "Nội dung")
