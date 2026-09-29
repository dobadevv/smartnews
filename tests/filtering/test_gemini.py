import json
import logging

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from smartnews.filtering.gemini import GeminiFilter
from smartnews.models import Article

ENDPOINT = "/v1beta/models/gemini-3.8-flash:generateContent"


def make_article(
    title: str = "Hello World", summary: str | None = "Original summary."
) -> Article:
    return Article(
        title=title,
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=summary,
    )


def gemini_response(title: str, summary: str) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps({"title": title, "summary": summary})}
                    ]
                }
            }
        ]
    }


def test_filter_replaces_title_and_summary_with_gemini_response(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("Tiêu đề ngắn gọn", "Tóm tắt ngắn gọn bằng tiếng Việt.")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article()

    result = gemini_filter.filter(article)

    assert result == Article(
        title="Tiêu đề ngắn gọn",
        url=article.url,
        source=article.source,
        published_at=None,
        summary="Tóm tắt ngắn gọn bằng tiếng Việt.",
    )


def test_filter_sends_the_api_key_as_a_header_not_in_the_url(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("T", "S")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )

    gemini_filter.filter(make_article())

    request = httpserver.log[0][0]
    assert request.headers.get("x-goog-api-key") == "fake-key"
    assert "fake-key" not in request.url


def test_filter_prompt_includes_title_and_summary(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("T", "S")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article(title="Original Title", summary="Original summary text")

    gemini_filter.filter(article)

    prompt = httpserver.log[0][0].get_json()["contents"][0]["parts"][0]["text"]
    assert "Original Title" in prompt
    assert "Original summary text" in prompt


def test_filter_keeps_original_article_when_request_fails(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500)
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article()

    with caplog.at_level(logging.ERROR):
        result = gemini_filter.filter(article)

    assert result == article
    messages = [record.getMessage() for record in caplog.records]
    assert any("500" in message for message in messages)
    assert not any("fake-key" in message for message in messages)


def test_filter_keeps_original_article_when_response_is_malformed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        {"candidates": []}
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article()

    result = gemini_filter.filter(article)

    assert result == article


def test_filter_next_call_succeeds_after_a_previous_call_failed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500)
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("Đã dịch", "Bản tóm tắt.")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )

    failing_result = gemini_filter.filter(make_article(title="Fails", summary="s1"))
    succeeding_result = gemini_filter.filter(
        make_article(title="Succeeds", summary="s2")
    )

    assert failing_result.title == "Fails"
    assert succeeding_result.title == "Đã dịch"
