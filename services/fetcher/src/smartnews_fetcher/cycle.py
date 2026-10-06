from smartnews_common.messaging.publisher import open_publisher
from smartnews_common.messaging.topology import ARTICLES_FETCHED
from sqlalchemy import Engine

from smartnews_fetcher.config import FetcherConfig
from smartnews_fetcher.pipeline import (
    Fetcher,
    stream_enabled_sources,
    stream_new_capped_to_max_posts,
    stream_published_within_lookback_days,
)
from smartnews_fetcher.publishing import TransactionalArticlePublisher


def run_cycle(
    config: FetcherConfig, fetcher: Fetcher, engine: Engine, rabbitmq_url: str
) -> int:
    sources = config.sources
    with open_publisher(rabbitmq_url, ARTICLES_FETCHED) as publisher:
        new_article_publisher = TransactionalArticlePublisher(
            engine=engine, publisher=publisher
        )
        fetched = stream_enabled_sources(sources, fetcher)
        recent = stream_published_within_lookback_days(fetched, sources)
        published = stream_new_capped_to_max_posts(recent, sources, new_article_publisher)
        return sum(1 for _ in published)
