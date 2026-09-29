import json
import logging

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Response

from smartnews.filtering.groq import GroqFilter
from smartnews.models import Article

ENDPOINT = "/openai/v1/chat/completions"


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


def groq_response(title: str, summary: str) -> dict:
    return {
        "choices": [
            {"message": {"content": json.dumps({"title": title, "summary": summary})}}
        ]
    }


def test_filter_replaces_title_and_summary_with_groq_response(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Tiêu đề ngắn gọn", "Tóm tắt ngắn gọn bằng tiếng Việt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article()

    result = groq_filter.filter(article)

    assert result == Article(
        title="Tiêu đề ngắn gọn",
        url=article.url,
        source=article.source,
        published_at=None,
        summary="Tóm tắt ngắn gọn bằng tiếng Việt.",
    )


def test_filter_sends_the_api_key_as_a_bearer_token_not_in_the_url(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("T", "S")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    groq_filter.filter(make_article())

    request = httpserver.log[0][0]
    assert request.headers.get("Authorization") == "Bearer fake-key"
    assert "fake-key" not in request.url


def test_filter_prompt_includes_title_and_summary(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("T", "S")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article(title="Original Title", summary="Original summary text")

    groq_filter.filter(article)

    messages = httpserver.log[0][0].get_json()["messages"]
    assert "Original Title" in messages[0]["content"]
    assert "Original summary text" in messages[0]["content"]


def test_filter_keeps_original_article_when_all_retries_fail(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article()

    with caplog.at_level(logging.ERROR):
        result = groq_filter.filter(article)

    assert result == article
    messages = [record.getMessage() for record in caplog.records]
    assert any("500" in message for message in messages)
    assert not any("fake-key" in message for message in messages)


def test_filter_recovers_from_a_transient_rate_limit_via_retry(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=429, headers={"Retry-After": "0.01"})
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Đã dịch", "Bản tóm tắt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    result = groq_filter.filter(make_article(title="Original", summary="s1"))

    assert result.title == "Đã dịch"
    assert result.summary == "Bản tóm tắt."


def test_filter_keeps_original_article_when_response_is_malformed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        {"choices": []}
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article()

    result = groq_filter.filter(article)

    assert result == article


def test_filter_next_call_is_unaffected_after_a_previous_call_exhausted_retries(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Đã dịch", "Bản tóm tắt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    failing_result = groq_filter.filter(make_article(title="Fails", summary="s1"))
    succeeding_result = groq_filter.filter(
        make_article(title="Succeeds", summary="s2")
    )

    assert failing_result.title == "Fails"
    assert succeeding_result.title == "Đã dịch"
