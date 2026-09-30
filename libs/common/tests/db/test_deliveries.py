import pytest
from smartnews_common.db.articles import ArticleStore
from smartnews_common.db.deliveries import DeliveryStore
from smartnews_common.models import Article
from sqlalchemy import Engine


@pytest.fixture
def article_id(engine: Engine) -> int:
    article = Article(
        title="Title", url="https://example.com/a", source="s", published_at=None, summary=None
    )
    with engine.begin() as connection:
        inserted_id = ArticleStore(connection).insert_if_absent(article)
    assert inserted_id is not None
    return inserted_id


@pytest.mark.parametrize(
    ("marked_channels", "queried_channel", "want"),
    [
        pytest.param([], "discord", False, id="never marked"),
        pytest.param(["discord"], "discord", True, id="marked on same channel"),
        pytest.param(["discord"], "telegram", False, id="marked on another channel only"),
        pytest.param(["discord", "discord"], "discord", True, id="marked twice"),
    ],
)
def test_is_delivered_reflects_marks_per_channel(
    engine: Engine,
    article_id: int,
    marked_channels: list[str],
    queried_channel: str,
    want: bool,
) -> None:
    for channel in marked_channels:
        with engine.begin() as connection:
            DeliveryStore(connection).mark_delivered(article_id, channel)

    with engine.connect() as connection:
        got = DeliveryStore(connection).is_delivered(article_id, queried_channel)

    assert got is want
