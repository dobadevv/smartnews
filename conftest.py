import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pika
import pytest
from alembic import command
from alembic.config import Config
from pika.adapters.blocking_connection import BlockingChannel
from smartnews_common.db.engine import create_database_engine
from smartnews_common.messaging.connection import open_confirmed_channel
from sqlalchemy import Engine, text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.rabbitmq import RabbitMqContainer

REPO_ROOT = Path(__file__).resolve().parent
APPLICATION_TABLES = "article_deliveries, article_transformations, articles"


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as container:
        url = container.get_connection_url(driver=None)
        alembic_config = Config(str(REPO_ROOT / "alembic.ini"))
        alembic_config.set_main_option("sqlalchemy.url", url)
        command.upgrade(alembic_config, "head")
        yield url


@pytest.fixture(scope="session")
def database_engine(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_database_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(database_engine: Engine) -> Engine:
    with database_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {APPLICATION_TABLES} RESTART IDENTITY"))
    return database_engine


Delivery = tuple[pika.spec.Basic.GetOk, pika.BasicProperties, bytes]


@pytest.fixture(scope="session")
def rabbitmq_url() -> Iterator[str]:
    with RabbitMqContainer("rabbitmq:4-alpine") as container:
        parameters = container.get_connection_params()
        yield (
            f"amqp://{container.username}:{container.password}"
            f"@{parameters.host}:{parameters.port}/%2F"
        )


@pytest.fixture
def rabbitmq_channel(rabbitmq_url: str) -> Iterator[BlockingChannel]:
    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    yield open_confirmed_channel(connection)
    connection.close()


@pytest.fixture
def unique_queue() -> str:
    return f"test.{uuid.uuid4().hex}"


@pytest.fixture
def wait_for_message(rabbitmq_channel: BlockingChannel) -> Callable[..., Delivery]:
    def wait(queue: str, timeout: float = 10.0) -> Delivery:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            method, properties, body = rabbitmq_channel.basic_get(queue, auto_ack=True)
            if method is not None:
                return method, properties, body
            rabbitmq_channel.connection.process_data_events(time_limit=0.05)
        pytest.fail(f"no message arrived on {queue} within {timeout}s")

    return wait


@pytest.fixture
def message_count(rabbitmq_channel: BlockingChannel) -> Callable[[str], int]:
    def count(queue: str) -> int:
        return rabbitmq_channel.queue_declare(queue, passive=True).method.message_count

    return count
