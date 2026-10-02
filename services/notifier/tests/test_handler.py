import logging

import pytest
from smartnews_common.messages import ArticleFetched, ArticleTransformed
from smartnews_common.messaging.consumer import DeliveryContext
from smartnews_common.models import Article
from smartnews_notifier.handler import (
    DeliveryError,
    NotificationHandler,
    NotificationHandlerDeps,
)


class FakeNotifier:
    def __init__(self, channel: str, *, error: Exception | None = None) -> None:
        self.channel = channel
        self.sent: list[Article] = []
        self._error = error

    def send(self, article: Article) -> None:
        if self._error is not None:
            raise self._error
        self.sent.append(article)


class FakeLedger:
    def __init__(self, delivered: set[tuple[int, str]] | None = None) -> None:
        self.delivered = set(delivered or set())

    def is_delivered(self, article_id: int, channel: str) -> bool:
        return (article_id, channel) in self.delivered

    def mark_delivered(self, article_id: int, channel: str) -> None:
        self.delivered.add((article_id, channel))


class UnusedPublisher:
    def publish(self, routing_key: str, message: object) -> None:
        raise AssertionError("the notification handler never publishes")


ARTICLE = Article(
    title="Tiêu đề", url="https://example.com/a", source="s", published_at=None, summary="Tóm tắt"
)
MESSAGE = ArticleTransformed.untranslated(ArticleFetched.from_article(ARTICLE, article_id=9))
CONTEXT = DeliveryContext(attempt=1, is_final_attempt=False, publisher=UnusedPublisher())


def make_handler(notifiers: list[FakeNotifier], ledger: FakeLedger) -> NotificationHandler:
    return NotificationHandler(NotificationHandlerDeps(notifiers=notifiers, ledger=ledger))


def test_handler_sends_to_every_channel_and_marks_each_delivered() -> None:
    discord, telegram = FakeNotifier("discord"), FakeNotifier("telegram")
    ledger = FakeLedger()

    make_handler([discord, telegram], ledger)(MESSAGE, CONTEXT)

    assert discord.sent == [ARTICLE] and telegram.sent == [ARTICLE]
    assert ledger.delivered == {(9, "discord"), (9, "telegram")}


def test_handler_skips_a_channel_that_already_received_the_article() -> None:
    discord, telegram = FakeNotifier("discord"), FakeNotifier("telegram")

    make_handler([discord, telegram], FakeLedger({(9, "discord")}))(MESSAGE, CONTEXT)

    assert (discord.sent, telegram.sent) == ([], [ARTICLE])


def test_handler_still_delivers_other_channels_then_raises_naming_the_failed_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    discord = FakeNotifier("discord", error=RuntimeError("webhook 500"))
    telegram = FakeNotifier("telegram")
    ledger = FakeLedger()

    with caplog.at_level(logging.ERROR), pytest.raises(DeliveryError) as raised:
        make_handler([discord, telegram], ledger)(MESSAGE, CONTEXT)

    assert raised.value.failed_channels == ["discord"]
    assert telegram.sent == [ARTICLE]
    assert ledger.delivered == {(9, "telegram")}
    assert any("discord" in record.getMessage() for record in caplog.records)


def test_redelivery_after_a_partial_failure_only_sends_to_the_failed_channel() -> None:
    discord, telegram = FakeNotifier("discord"), FakeNotifier("telegram")
    ledger = FakeLedger({(9, "telegram")})

    make_handler([discord, telegram], ledger)(MESSAGE, CONTEXT)

    assert (discord.sent, telegram.sent) == ([ARTICLE], [])


def test_handler_with_no_enabled_channel_acks_without_marking_anything() -> None:
    ledger = FakeLedger()

    make_handler([], ledger)(MESSAGE, CONTEXT)

    assert ledger.delivered == set()
