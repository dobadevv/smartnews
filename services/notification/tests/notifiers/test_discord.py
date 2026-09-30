import json
import logging

import discord
import pytest
import responses
from smartnews_common.models import Article
from smartnews_notification.notifiers.discord import DiscordNotifier

WEBHOOK_ID = "123456789012345678"
WEBHOOK_TOKEN = "some-secret-token-" + "a" * 50
WEBHOOK_URL = f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}"
WEBHOOK_ENDPOINT = f"https://discord.com/api/v10/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}"


def _sent_body() -> dict[str, object]:
    return json.loads(responses.calls[0].request.body)


@responses.activate
def test_send_posts_a_bare_embed_when_no_category_summary_or_thumbnail() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send(article)

    embed = _sent_body()["embeds"][0]
    assert embed["title"] == "Hello World"
    assert embed["url"] == "https://example.com/hello-world"
    assert "description" not in embed
    assert "image" not in embed


@responses.activate
def test_send_includes_category_and_summary_in_embed() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="A short summary.",
        category="Tech",
    )

    notifier.send(article)

    embed = _sent_body()["embeds"][0]
    assert embed["title"] == "[Tech] Hello World"
    assert embed["description"] == "```A short summary.```"


@responses.activate
def test_send_includes_thumbnail_as_a_large_image_in_embed_when_present() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
        thumbnail="https://example.com/hello-world.jpg",
    )

    notifier.send(article)

    embed = _sent_body()["embeds"][0]
    assert embed["image"] == {"url": "https://example.com/hello-world.jpg"}
    assert "thumbnail" not in embed


@responses.activate
def test_send_raises_when_webhook_returns_an_error() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=400)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with pytest.raises(discord.HTTPException):
        notifier.send(article)


@responses.activate
def test_send_logs_payload_and_response_when_webhook_returns_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.add(
        responses.POST,
        WEBHOOK_ENDPOINT,
        json={"message": "Invalid Form Body", "code": 50035},
        status=400,
    )
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(discord.HTTPException):
        notifier.send(article)

    messages = [record.getMessage() for record in caplog.records]
    assert any("400" in message for message in messages)
    assert any("Hello World" in message for message in messages)
    assert any("Invalid Form Body" in message for message in messages)
    assert not any(WEBHOOK_TOKEN in message for message in messages)


@responses.activate
def test_send_truncates_long_title_to_fit_discords_title_limit() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="x" * 300,
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send(article)

    title = _sent_body()["embeds"][0]["title"]
    assert len(title) <= 256
    assert title.startswith("xxx")
    assert "…" in title


@responses.activate
def test_send_truncates_long_summary_to_fit_discords_description_limit() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="x" * 5000,
    )

    notifier.send(article)

    description = _sent_body()["embeds"][0]["description"]
    assert len(description) <= 4096
    assert description.startswith("```x")
    assert description.endswith("```")
    assert "…" in description


@responses.activate
def test_send_escapes_discord_markdown_special_characters_in_title() -> None:
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="AI_powered *thing*",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send(article)

    title = _sent_body()["embeds"][0]["title"]
    assert title == r"AI\_powered \*thing\*"


@responses.activate
def test_send_escapes_triple_backticks_in_summary_to_avoid_breaking_the_code_fence() -> (
    None
):
    responses.add(responses.POST, WEBHOOK_ENDPOINT, status=204)
    notifier = DiscordNotifier(WEBHOOK_URL)
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="before ```escape me``` after",
    )

    notifier.send(article)

    description = _sent_body()["embeds"][0]["description"]
    assert description.startswith("```before")
    assert description.endswith("after```")
    assert "```escape me```" not in description
