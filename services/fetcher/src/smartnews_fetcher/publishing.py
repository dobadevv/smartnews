from smartnews_common.db.articles import ArticleStore
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.publisher import MessagePublisher
from smartnews_common.messaging.topology import ARTICLES_FETCHED
from smartnews_common.models import Article
from sqlalchemy import Engine


class TransactionalArticlePublisher:
    """Stores and publishes an article in one transaction.

    The row only commits once the broker confirmed the message, so a failed
    publish leaves the article new and it is retried on the next cycle.
    """

    def __init__(self, engine: Engine, publisher: MessagePublisher) -> None:
        self._engine = engine
        self._publisher = publisher

    def publish_if_new(self, article: Article) -> bool:
        with self._engine.begin() as connection:
            article_id = ArticleStore(connection).insert_if_absent(article)
            if article_id is None:
                return False
            self._publisher.publish(
                ARTICLES_FETCHED, ArticleFetched.from_article(article, article_id)
            )
        return True
