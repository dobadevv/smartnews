import logging

import pytest
from pytest_httpserver import HTTPServer
from smartnews_common.models import Article
from smartnews_notification.notifiers.telegram import TelegramNotifier
from smartnews_notification.text import html_to_text
from telegram.error import TelegramError

BOT_TOKEN = "fake-token"


def _expect_get_me(httpserver: HTTPServer) -> None:
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/getMe", method="POST"
    ).respond_with_json(
        {"ok": True, "result": {"id": 1, "is_bot": True, "first_name": "TestBot"}}
    )


def _last_request_body(httpserver: HTTPServer) -> dict[str, object]:
    return dict(httpserver.log[-1][0].form)


def _ok_message_response() -> dict[str, object]:
    return {
        "ok": True,
        "result": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 12345, "type": "private"},
        },
    }


def test_send_posts_each_article_to_the_bot_api(httpserver: HTTPServer) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    notifier.send(article)

    body = _last_request_body(httpserver)
    assert body["chat_id"] == "12345"
    assert body["parse_mode"] == "HTML"
    assert body["text"] == (
        "<b>🔥🔥 Hello World 🔥🔥</b>\n\n🔗 https://example.com/hello-world"
    )


def test_send_includes_category_and_summary_in_text_when_no_thumbnail(
    httpserver: HTTPServer,
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
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

    body = _last_request_body(httpserver)
    assert body["text"] == (
        "<b>🔥🔥 [Tech] Hello World 🔥🔥</b>\n\n"
        "<blockquote>A short summary.</blockquote>\n\n"
        "🔗 https://example.com/hello-world"
    )


def test_send_posts_photo_with_caption_when_thumbnail_present(
    httpserver: HTTPServer,
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendPhoto", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
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

    body = _last_request_body(httpserver)
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
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendPhoto", method="POST"
    ).respond_with_json(
        {"ok": False, "description": "Bad Request: photo failed"}, status=400
    )
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
        thumbnail="https://example.com/hello-world.jpg",
    )

    with pytest.raises(TelegramError):
        notifier.send(article)


def test_send_raises_when_bot_api_returns_an_error(httpserver: HTTPServer) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(
        {"ok": False, "description": "Bad Request: message text is empty"}, status=400
    )
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with pytest.raises(TelegramError):
        notifier.send(article)


def test_send_logs_payload_and_response_when_bot_api_returns_an_error(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(
        {"ok": False, "description": "Bad Request: article rejected by moderation"},
        status=400,
    )
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    with caplog.at_level(logging.ERROR), pytest.raises(TelegramError):
        notifier.send(article)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Hello World" in message for message in messages)
    assert any("Article rejected by moderation" in message for message in messages)
    assert not any(BOT_TOKEN in message for message in messages)


def test_send_truncates_long_summary_to_fit_telegrams_message_limit(
    httpserver: HTTPServer,
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary="x" * 5000,
    )

    notifier.send(article)

    text = _last_request_body(httpserver)["text"]
    rendered = html_to_text(text)
    assert rendered is not None
    assert len(rendered) <= 4096
    assert rendered.startswith("🔥🔥 Hello World 🔥🔥")
    assert rendered.endswith("🔗 https://example.com/hello-world")
    assert "…" in rendered


def test_send_truncates_long_caption_to_fit_telegrams_caption_limit(
    httpserver: HTTPServer,
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendPhoto", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
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

    caption = _last_request_body(httpserver)["caption"]
    rendered = html_to_text(caption)
    assert rendered is not None
    assert len(rendered) <= 1024
    assert rendered.startswith("🔥🔥 Hello World 🔥🔥")
    assert rendered.endswith("🔗 https://example.com/hello-world")
    assert "…" in rendered


def test_send_escapes_html_special_characters_in_title_and_summary(
    httpserver: HTTPServer,
) -> None:
    _expect_get_me(httpserver)
    httpserver.expect_request(
        f"/bot{BOT_TOKEN}/sendMessage", method="POST"
    ).respond_with_json(_ok_message_response())
    notifier = TelegramNotifier(
        api_base_url=httpserver.url_for(""), bot_token=BOT_TOKEN, chat_id="12345"
    )
    article = Article(
        title="Fish & Chips <Yum>",
        url="https://example.com/hello-world?a=1&b=2",
        source="example-blog",
        published_at=None,
        summary="Rated 5 > 4 stars",
    )

    notifier.send(article)

    text = _last_request_body(httpserver)["text"]
    assert "<b>🔥🔥 Fish &amp; Chips &lt;Yum&gt; 🔥🔥</b>" in text
    assert "<blockquote>Rated 5 &gt; 4 stars</blockquote>" in text
    assert "🔗 https://example.com/hello-world?a=1&amp;b=2" in text
    assert html_to_text(text) == (
        "🔥🔥 Fish & Chips <Yum> 🔥🔥 Rated 5 > 4 stars "
        "🔗 https://example.com/hello-world?a=1&b=2"
    )
