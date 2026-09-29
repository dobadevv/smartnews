import logging

import pytest
import requests
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from smartnews.models import Article
from smartnews.notifiers.telegram import TelegramNotifier
from smartnews.text import html_to_text


def test_send_posts_each_article_to_the_bot_api(httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send(article)

    received_requests = httpserver.log
    assert len(received_requests) == 1
    body = received_requests[0][0].get_json()
    assert body["chat_id"] == "12345"
    assert body["parse_mode"] == "HTML"
    assert body["text"] == (
        "<b>🔥🔥 Hello World 🔥🔥</b>\n\n🔗 https://example.com/hello-world"
    )


def test_send_includes_category_and_summary_in_text_when_no_thumbnail(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="A short summary.",
        category="Tech",
    )

    notifier.send(article)

    body = httpserver.log[0][0].get_json()
    assert body["text"] == (
        "<b>🔥🔥 [Tech] Hello World 🔥🔥</b>\n\n"
        "<blockquote>A short summary.</blockquote>\n\n"
        "🔗 https://example.com/hello-world"
    )


def test_send_posts_photo_with_caption_when_thumbnail_present(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendPhoto", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="A short summary.",
        thumbnail="https://example.com/hello-world.jpg",
        category="Tech",
    )

    notifier.send(article)

    received_requests = httpserver.log
    assert len(received_requests) == 1
    body = received_requests[0][0].get_json()
    assert body["chat_id"] == "12345"
    assert body["parse_mode"] == "HTML"
    assert body["photo"] == "https://example.com/hello-world.jpg"
    assert body["caption"] == (
        "<b>🔥🔥 [Tech] Hello World 🔥🔥</b>\n\n"
        "<blockquote>A short summary.</blockquote>\n\n"
        "🔗 https://example.com/hello-world"
    )


def test_send_raises_when_bot_api_returns_an_error_for_photo(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendPhoto", method="POST"
    ).respond_with_response(Response(status=500))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
        thumbnail="https://example.com/hello-world.jpg",
    )

    with pytest.raises(requests.exceptions.HTTPError):
        notifier.send(article)


def test_send_raises_when_bot_api_returns_an_error(httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_response(Response(status=500))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with pytest.raises(requests.exceptions.HTTPError):
        notifier.send(article)


def test_send_logs_payload_and_response_when_bot_api_returns_an_error(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_json(
        {"ok": False, "description": "Bad Request: message text is empty"},
        status=400,
    )
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(requests.exceptions.HTTPError):
        notifier.send(article)

    messages = [record.getMessage() for record in caplog.records]
    assert any("400" in message for message in messages)
    assert any("Hello World" in message for message in messages)
    assert any("Bad Request: message text is empty" in message for message in messages)
    assert not any("fake-token" in message for message in messages)


def test_send_truncates_long_summary_to_fit_telegrams_message_limit(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="x" * 5000,
    )

    notifier.send(article)

    text = httpserver.log[0][0].get_json()["text"]
    rendered = html_to_text(text)
    assert rendered is not None
    assert len(rendered) <= 4096
    assert rendered.startswith("🔥🔥 Hello World 🔥🔥")
    assert rendered.endswith("🔗 https://example.com/hello-world")
    assert "…" in rendered


def test_send_truncates_long_caption_to_fit_telegrams_caption_limit(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendPhoto", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="x" * 5000,
        thumbnail="https://example.com/hello-world.jpg",
    )

    notifier.send(article)

    caption = httpserver.log[0][0].get_json()["caption"]
    rendered = html_to_text(caption)
    assert rendered is not None
    assert len(rendered) <= 1024
    assert rendered.startswith("🔥🔥 Hello World 🔥🔥")
    assert rendered.endswith("🔗 https://example.com/hello-world")
    assert "…" in rendered


def test_send_escapes_html_special_characters_in_title_and_summary(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(
        "/botfake-token/sendMessage", method="POST"
    ).respond_with_response(Response(status=200))
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token="fake-token", chat_id="12345"
    )
    article = Article(
        title="Fish & Chips <Yum>",
        url="https://example.com/hello-world?a=1&b=2",
        source="example-blog",
        published_at=None,
        summary="Rated 5 > 4 stars",
    )

    notifier.send(article)

    text = httpserver.log[0][0].get_json()["text"]
    assert "<b>🔥🔥 Fish &amp; Chips &lt;Yum&gt; 🔥🔥</b>" in text
    assert "<blockquote>Rated 5 &gt; 4 stars</blockquote>" in text
    assert "🔗 https://example.com/hello-world?a=1&amp;b=2" in text
    assert html_to_text(text) == (
        "🔥🔥 Fish & Chips <Yum> 🔥🔥 Rated 5 > 4 stars "
        "🔗 https://example.com/hello-world?a=1&b=2"
    )
