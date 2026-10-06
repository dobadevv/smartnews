import logging
import threading

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.exceptions import AMQPChannelError
from smartnews_common.db.articles import ArticleStore
from smartnews_common.db.generated.articles import ListUntransformedArticlesRow
from smartnews_common.messages import ArticleFetched
from smartnews_common.messaging.connection import (
    connection_parameters,
    open_confirmed_channel,
)
from smartnews_common.messaging.topology import ARTICLES_FETCHED
from sqlalchemy import Engine

from smartnews_redriver.republish import republish_to_queue, stopped_while_pausing

logger = logging.getLogger(__name__)


def run_retransform_pass(
    engine: Engine,
    rabbitmq_url: str,
    min_age_minutes: int,
    delay_seconds: float,
    max_messages_per_run: int,
    stop_requested: threading.Event,
) -> None:
    articles = select_untransformed_articles(
        engine=engine, min_age_minutes=min_age_minutes, limit=max_messages_per_run
    )
    republished = 0
    if articles:
        republished = _republish_over_new_connection(
            rabbitmq_url=rabbitmq_url,
            articles=articles,
            delay_seconds=delay_seconds,
            stop_requested=stop_requested,
        )
    logger.info(
        "republished %d of %d untransformed article(s) to %s (limit %d)",
        republished,
        len(articles),
        ARTICLES_FETCHED,
        max_messages_per_run,
    )


def select_untransformed_articles(
    engine: Engine, min_age_minutes: int, limit: int
) -> list[ListUntransformedArticlesRow]:
    # The connection is released before publishing so it is never held open
    # across the per-message delays.
    with engine.connect() as connection:
        return ArticleStore(connection).list_untransformed(
            min_age_minutes=min_age_minutes, limit=limit
        )


def republish_articles(
    channel: BlockingChannel,
    articles: list[ListUntransformedArticlesRow],
    delay_seconds: float,
    stop_requested: threading.Event,
) -> int:
    republished = 0
    for position, article in enumerate(articles):
        if _stop_requested_before(
            position=position,
            stop_requested=stop_requested,
            delay_seconds=delay_seconds,
        ):
            break
        try:
            republish_to_queue(
                channel=channel,
                queue=ARTICLES_FETCHED,
                body=_as_article_fetched(article).model_dump_json().encode(),
            )
        except AMQPChannelError:
            logger.exception(
                "failed to republish article_id=%d to %s after %d republished;"
                " aborting this pass",
                article.id,
                ARTICLES_FETCHED,
                republished,
            )
            break
        republished += 1
    return republished


def _open_connection(rabbitmq_url: str) -> pika.BlockingConnection:
    return pika.BlockingConnection(connection_parameters(rabbitmq_url))


def _republish_over_new_connection(
    rabbitmq_url: str,
    articles: list[ListUntransformedArticlesRow],
    delay_seconds: float,
    stop_requested: threading.Event,
) -> int:
    connection = _open_connection(rabbitmq_url)
    try:
        channel = open_confirmed_channel(connection)
        return republish_articles(
            channel=channel,
            articles=articles,
            delay_seconds=delay_seconds,
            stop_requested=stop_requested,
        )
    finally:
        # A connection the broker already dropped cannot be closed again, and
        # trying would replace the error that dropped it.
        if connection.is_open:
            connection.close()


def _stop_requested_before(
    position: int, stop_requested: threading.Event, delay_seconds: float
) -> bool:
    if position == 0:
        return stop_requested.is_set()
    return stopped_while_pausing(
        stop_requested=stop_requested, delay_seconds=delay_seconds
    )


def _as_article_fetched(article: ListUntransformedArticlesRow) -> ArticleFetched:
    # The stored hash_url is reused rather than recomputed so the message
    # matches the database row exactly.
    return ArticleFetched(
        article_id=article.id,
        hash_url=article.hash_url,
        url=article.url,
        title=article.title,
        summary=article.summary,
        published_at=article.published_at,
        source=article.source,
        thumbnail=article.thumbnail,
        category=article.category,
    )
