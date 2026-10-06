from smartnews_common.db.articles import ArticleStore
from smartnews_common.models import Article
from smartnews_notifier.ledger import DatabaseDeliveryLedger
from sqlalchemy import Engine


def test_ledger_marks_and_reads_deliveries_per_channel(engine: Engine) -> None:
    article = Article(title="T", url="https://example.com/a", source="s", published_at=None, summary=None)
    with engine.begin() as connection:
        article_id = ArticleStore(connection).insert_if_absent(article)
    assert article_id is not None
    ledger = DatabaseDeliveryLedger(engine)

    ledger.mark_delivered(article_id, "discord")

    assert ledger.is_delivered(article_id, "discord") is True
    assert ledger.is_delivered(article_id, "telegram") is False
