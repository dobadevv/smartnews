import json
import logging

import pytest
from pytest_httpserver import HTTPServer
from smartnews_common.models import Article, Transformation
from smartnews_transformer.filtering.base import TransformationError
from smartnews_transformer.filtering.opencode_go import (
    DEFAULT_MODEL,
    USER_AGENT,
    OpencodeGoFilter,
)
from werkzeug.wrappers import Response

ENDPOINT = "/chat/completions"


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


def opencode_go_response(title: str, summary: str) -> dict:
    return {
        "choices": [
            {"message": {"content": json.dumps({"title": title, "summary": summary})}}
        ]
    }


def make_filter(httpserver: HTTPServer) -> OpencodeGoFilter:
    return OpencodeGoFilter(api_key="fake-key", api_base_url=httpserver.url_for(""))


def test_transform_replaces_title_and_summary_with_opencode_go_response(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("Tiêu đề ngắn gọn", "Tóm tắt ngắn gọn bằng tiếng Việt.")
    )

    result = make_filter(httpserver).transform(make_article())

    assert result == Transformation(
        title="Tiêu đề ngắn gọn",
        summary="Tóm tắt ngắn gọn bằng tiếng Việt.",
        language="vi",
    )


def test_transform_requests_json_from_the_default_model(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("T", "S")
    )

    make_filter(httpserver).transform(make_article())

    body = httpserver.log[0][0].get_json()
    assert body["model"] == DEFAULT_MODEL
    assert body["response_format"] == {"type": "json_object"}


def test_transform_prompt_includes_title_and_summary(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("T", "S")
    )

    make_filter(httpserver).transform(
        make_article(title="Original Title", summary="Original summary text")
    )

    messages = httpserver.log[0][0].get_json()["messages"]
    assert "Original Title" in messages[0]["content"]
    assert "Original summary text" in messages[0]["content"]


def test_transform_sends_the_api_key_as_a_bearer_token_not_in_the_url(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("T", "S")
    )

    make_filter(httpserver).transform(make_article())

    request = httpserver.log[0][0]
    assert request.headers.get("Authorization") == "Bearer fake-key"
    assert "fake-key" not in request.url


def test_transform_identifies_with_its_own_user_agent(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("T", "S")
    )

    make_filter(httpserver).transform(make_article())

    assert httpserver.log[0][0].headers.get("User-Agent") == USER_AGENT


def test_transform_sends_the_same_session_id_on_every_request(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_response("T", "S")
    )
    opencode_go_filter = make_filter(httpserver)

    opencode_go_filter.transform(make_article())
    opencode_go_filter.transform(make_article())

    session_ids = [
        request.headers.get("x-opencode-session") for request, _ in httpserver.log
    ]
    assert session_ids[0]
    assert session_ids[0] == session_ids[1]


def test_transform_raises_transformation_error_when_all_retries_fail(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )

    with caplog.at_level(logging.ERROR), pytest.raises(
        TransformationError, match="hello-world"
    ):
        make_filter(httpserver).transform(make_article())

    messages = [record.getMessage() for record in caplog.records]
    assert any("500" in message for message in messages)
    assert not any("fake-key" in message for message in messages)


def test_transform_raises_transformation_error_when_response_is_malformed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        {"choices": []}
    )

    with pytest.raises(TransformationError):
        make_filter(httpserver).transform(make_article())
