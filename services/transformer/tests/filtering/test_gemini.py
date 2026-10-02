import json
import logging

import pytest
from pytest_httpserver import HTTPServer
from smartnews_common.models import Article, Transformation
from smartnews_transformer.filtering.base import TransformationError
from smartnews_transformer.filtering.gemini import GeminiFilter
from werkzeug.wrappers import Response

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


def gemini_text_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def gemini_response(title: str, summary: str) -> dict:
    return gemini_text_response(json.dumps({"title": title, "summary": summary}))


def test_transform_replaces_title_and_summary_with_gemini_response(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("Tiêu đề ngắn gọn", "Tóm tắt ngắn gọn bằng tiếng Việt.")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article()

    result = gemini_filter.transform(article)

    assert result == Transformation(
        title="Tiêu đề ngắn gọn",
        summary="Tóm tắt ngắn gọn bằng tiếng Việt.",
        language="vi",
    )


def test_transform_sends_the_api_key_as_a_header_not_in_the_url(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("T", "S")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )

    gemini_filter.transform(make_article())

    request = httpserver.log[0][0]
    assert request.headers.get("x-goog-api-key") == "fake-key"
    assert "fake-key" not in request.url


def test_transform_prompt_includes_title_and_summary(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("T", "S")
    )
    gemini_filter = GeminiFilter(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )
    article = make_article(title="Original Title", summary="Original summary text")

    gemini_filter.transform(article)

    prompt = httpserver.log[0][0].get_json()["contents"][0]["parts"][0]["text"]
    assert "Original Title" in prompt
    assert "Original summary text" in prompt


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transform_raises_transformation_error_when_request_fails(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=status)
    )
    gemini_filter = GeminiFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with caplog.at_level(logging.ERROR), pytest.raises(TransformationError, match="hello-world"):
        gemini_filter.transform(make_article())

    messages = [record.getMessage() for record in caplog.records]
    assert any(str(status) in message for message in messages)
    assert not any("fake-key" in message for message in messages)


def test_transform_raises_transformation_error_when_response_is_malformed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json({"candidates": []})
    gemini_filter = GeminiFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with pytest.raises(TransformationError):
        gemini_filter.transform(make_article())


def test_transform_next_call_succeeds_after_a_previous_call_failed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500)
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("Đã dịch", "Bản tóm tắt.")
    )
    gemini_filter = GeminiFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with pytest.raises(TransformationError):
        gemini_filter.transform(make_article(title="Fails", summary="s1"))
    succeeding_result = gemini_filter.transform(make_article(title="Succeeds", summary="s2"))

    assert succeeding_result.title == "Đã dịch"


def test_transform_asks_gemini_for_a_json_object_with_title_and_summary(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_response("T", "S")
    )
    gemini_filter = GeminiFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    gemini_filter.transform(make_article())

    generation_config = httpserver.log[0][0].get_json()["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert set(generation_config["responseSchema"]["properties"]) == {"title", "summary"}


@pytest.mark.parametrize(
    "response_body",
    [
        {"promptFeedback": {"blockReason": "SAFETY"}},
        gemini_text_response(json.dumps({"title": "Only a title"})),
        gemini_text_response("this is not json"),
    ],
    ids=["prompt-blocked", "summary-missing", "text-is-not-json"],
)
def test_transform_raises_transformation_error_when_gemini_returns_no_usable_result(
    httpserver: HTTPServer, response_body: dict
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(response_body)
    gemini_filter = GeminiFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))

    with pytest.raises(TransformationError, match="hello-world"):
        gemini_filter.transform(make_article())
