import pytest
from smartnews_common.db.articles import ArticleStore
from smartnews_common.db.transformations import TransformationStore
from smartnews_common.models import Article, Transformation
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def article_id(engine: Engine) -> int:
    article = Article(
        title="Title", url="https://example.com/a", source="s", published_at=None, summary=None
    )
    with engine.begin() as connection:
        inserted_id = ArticleStore(connection).insert_if_absent(article)
    assert inserted_id is not None
    return inserted_id


def read_transformation(engine: Engine, article_id: int) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text("SELECT title, summary, language FROM article_transformations WHERE article_id = :id"),
                {"id": article_id},
            ).mappings().one()
        )


def test_upsert_stores_the_transformation(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert(
            article_id, Transformation(title="Tiêu đề", summary="Tóm tắt", language="vi")
        )

    assert read_transformation(engine, article_id) == {
        "title": "Tiêu đề", "summary": "Tóm tắt", "language": "vi"
    }


def test_upsert_overwrites_an_existing_transformation(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert(
            article_id, Transformation(title="Cũ", summary="Cũ", language="vi")
        )
    with engine.begin() as connection:
        TransformationStore(connection).upsert(
            article_id, Transformation(title="Mới", summary=None, language="vi")
        )

    assert read_transformation(engine, article_id) == {
        "title": "Mới", "summary": None, "language": "vi"
    }


def test_upsert_rejects_a_language_other_than_vietnamese(engine: Engine, article_id: int) -> None:
    unsupported = Transformation(title="T", summary=None, language="en")  # type: ignore[arg-type]

    with pytest.raises(IntegrityError), engine.begin() as connection:
        TransformationStore(connection).upsert(article_id, unsupported)


def read_content_row(engine: Engine, article_id: int) -> dict:
    with engine.connect() as connection:
        return dict(
            connection.execute(
                text(
                    "SELECT title, summary, language, content "
                    "FROM article_transformations WHERE article_id = :id"
                ),
                {"id": article_id},
            ).mappings().one()
        )


def test_upsert_content_creates_a_row_without_title_when_none_exists(
    engine: Engine, article_id: int
) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert_content(article_id, "Nội dung")

    assert read_content_row(engine, article_id) == {
        "title": None, "summary": None, "language": "vi", "content": "Nội dung"
    }


def test_upsert_content_keeps_the_title_and_summary_already_recorded(
    engine: Engine, article_id: int
) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert(
            article_id, Transformation(title="Tiêu đề", summary="Tóm tắt", language="vi")
        )
    with engine.begin() as connection:
        TransformationStore(connection).upsert_content(article_id, "Nội dung")

    assert read_content_row(engine, article_id) == {
        "title": "Tiêu đề", "summary": "Tóm tắt", "language": "vi", "content": "Nội dung"
    }


def test_upsert_keeps_the_content_already_recorded(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert_content(article_id, "Nội dung")
    with engine.begin() as connection:
        TransformationStore(connection).upsert(
            article_id, Transformation(title="Tiêu đề", summary="Tóm tắt", language="vi")
        )

    assert read_content_row(engine, article_id) == {
        "title": "Tiêu đề", "summary": "Tóm tắt", "language": "vi", "content": "Nội dung"
    }


def test_upsert_content_overwrites_an_existing_content(engine: Engine, article_id: int) -> None:
    with engine.begin() as connection:
        TransformationStore(connection).upsert_content(article_id, "Cũ")
    with engine.begin() as connection:
        TransformationStore(connection).upsert_content(article_id, "Mới")

    assert read_content_row(engine, article_id)["content"] == "Mới"
