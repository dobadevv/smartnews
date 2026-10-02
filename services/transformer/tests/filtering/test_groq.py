import json
import logging

import pytest
from pytest_httpserver import HTTPServer
from smartnews_common.models import Article, Transformation
from smartnews_transformer.filtering.base import TransformationError
from smartnews_transformer.filtering.groq import GroqFilter
from werkzeug.wrappers import Response

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


def test_transform_replaces_title_and_summary_with_groq_response(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Tiêu đề ngắn gọn", "Tóm tắt ngắn gọn bằng tiếng Việt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article()

    result = groq_filter.transform(article)

    assert result == Transformation(
        title="Tiêu đề ngắn gọn",
        summary="Tóm tắt ngắn gọn bằng tiếng Việt.",
        language="vi",
    )


def test_transform_sends_the_api_key_as_a_bearer_token_not_in_the_url(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("T", "S")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    groq_filter.transform(make_article())

    request = httpserver.log[0][0]
    assert request.headers.get("Authorization") == "Bearer fake-key"
    assert "fake-key" not in request.url


def test_transform_prompt_includes_title_and_summary(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("T", "S")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))
    article = make_article(title="Original Title", summary="Original summary text")

    groq_filter.transform(article)

    messages = httpserver.log[0][0].get_json()["messages"]
    assert "Original Title" in messages[0]["content"]
    assert "Original summary text" in messages[0]["content"]


def test_transform_raises_transformation_error_when_all_retries_fail(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with caplog.at_level(logging.ERROR), pytest.raises(TransformationError, match="hello-world"):
        groq_filter.transform(make_article())

    messages = [record.getMessage() for record in caplog.records]
    assert any("500" in message for message in messages)
    assert not any("fake-key" in message for message in messages)


def test_transform_recovers_from_a_transient_rate_limit_via_retry(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=429, headers={"Retry-After": "0.01"})
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Đã dịch", "Bản tóm tắt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    result = groq_filter.transform(make_article(title="Original", summary="s1"))

    assert result.title == "Đã dịch"
    assert result.summary == "Bản tóm tắt."


def test_transform_raises_transformation_error_when_response_is_malformed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json({"choices": []})
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with pytest.raises(TransformationError):
        groq_filter.transform(make_article())


def test_transform_keeps_retrying_past_the_sdk_retry_budget_while_rate_limited(
    httpserver: HTTPServer,
) -> None:
    for _ in range(3):
        httpserver.expect_ordered_request(
            ENDPOINT, method="POST"
        ).respond_with_response(Response(status=429, headers={"Retry-After": "0.01"}))
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Đã dịch", "Bản tóm tắt.")
    )
    groq_filter = GroqFilter(
        api_key="fake-key",
        api_base_url=httpserver.url_for(""),
        rate_limit_timeout=5,
    )

    result = groq_filter.transform(make_article(title="Original", summary="s1"))

    assert result.title == "Đã dịch"
    assert result.summary == "Bản tóm tắt."


def test_transform_raises_transformation_error_when_rate_limit_outlasts_the_timeout(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=429, headers={"Retry-After": "0.05"})
    )
    groq_filter = GroqFilter(
        api_key="fake-key", api_base_url=httpserver.url_for(""), rate_limit_timeout=0.05
    )

    with caplog.at_level(logging.ERROR), pytest.raises(TransformationError):
        groq_filter.transform(make_article())

    assert any("429" in record.getMessage() for record in caplog.records)


def test_transform_next_call_is_unaffected_after_a_previous_call_exhausted_retries(
    httpserver: HTTPServer,
) -> None:
    for _ in range(3):
        httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
            Response(status=500, headers={"Retry-After": "0.01"})
        )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        groq_response("Đã dịch", "Bản tóm tắt.")
    )
    groq_filter = GroqFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with pytest.raises(TransformationError):
        groq_filter.transform(make_article(title="Fails", summary="s1"))
    succeeding_result = groq_filter.transform(make_article(title="Succeeds", summary="s2"))

    assert succeeding_result.title == "Đã dịch"
