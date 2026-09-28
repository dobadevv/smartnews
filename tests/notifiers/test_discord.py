import logging

import pytest
import requests
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from smartnews.models import Article
from smartnews.notifiers.discord import DiscordNotifier


def test_send_posts_a_bare_embed_when_no_category_summary_or_thumbnail(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send([article])

    embed = httpserver.log[0][0].get_json()["embeds"][0]
    assert embed == {
        "title": "🔥🔥 Hello World 🔥🔥",
        "url": "https://example.com/hello-world",
    }


def test_send_includes_category_and_summary_in_embed(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="A short summary.",
        category="Tech",
    )

    notifier.send([article])

    embed = httpserver.log[0][0].get_json()["embeds"][0]
    assert embed["title"] == "🔥🔥 [Tech] Hello World 🔥🔥"
    assert embed["description"] == "```A short summary.```"


def test_send_includes_thumbnail_as_a_large_image_in_embed_when_present(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
        thumbnail="https://example.com/hello-world.jpg",
    )

    notifier.send([article])

    embed = httpserver.log[0][0].get_json()["embeds"][0]
    assert embed["image"] == {"url": "https://example.com/hello-world.jpg"}
    assert "thumbnail" not in embed


def test_send_raises_when_webhook_returns_an_error(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=500)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with pytest.raises(requests.exceptions.HTTPError):
        notifier.send([article])


def test_send_logs_payload_and_response_when_webhook_returns_an_error(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(
        "/webhook/some-secret-token", method="POST"
    ).respond_with_json({"message": "Invalid Form Body", "code": 50035}, status=400)
    notifier = DiscordNotifier(httpserver.url_for("/webhook/some-secret-token"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(requests.exceptions.HTTPError):
        notifier.send([article])

    messages = [record.getMessage() for record in caplog.records]
    assert any("400" in message for message in messages)
    assert any("Hello World" in message for message in messages)
    assert any("Invalid Form Body" in message for message in messages)
    assert not any("some-secret-token" in message for message in messages)


def test_send_truncates_long_title_to_fit_discords_title_limit(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="x" * 300,
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send([article])

    title = httpserver.log[0][0].get_json()["embeds"][0]["title"]
    assert len(title) <= 256
    assert title.startswith("🔥🔥 xxx")
    assert "…" in title


def test_send_truncates_long_summary_to_fit_discords_description_limit(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="x" * 5000,
    )

    notifier.send([article])

    description = httpserver.log[0][0].get_json()["embeds"][0]["description"]
    assert len(description) <= 4096
    assert description.startswith("```x")
    assert description.endswith("```")
    assert "…" in description


def test_send_escapes_discord_markdown_special_characters_in_title(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="AI_powered *thing*",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send([article])

    title = httpserver.log[0][0].get_json()["embeds"][0]["title"]
    assert title == r"🔥🔥 AI\_powered \*thing\* 🔥🔥"


def test_send_escapes_triple_backticks_in_summary_to_avoid_breaking_the_code_fence(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request("/webhook", method="POST").respond_with_response(
        Response(status=204)
    )
    notifier = DiscordNotifier(httpserver.url_for("/webhook"))
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="before ```escape me``` after",
    )

    notifier.send([article])

    description = httpserver.log[0][0].get_json()["embeds"][0]["description"]
    assert description.startswith("```before")
    assert description.endswith("after```")
    assert "```escape me```" not in description
