import pytest
from pytest_httpserver import HTTPServer
from smartnews_transformer.filtering.base import TransformationError
from smartnews_transformer.filtering.opencode_go import OpencodeGoContentTranslator
from smartnews_transformer.filtering.prompts import MAX_CONTENT_CHARS
from werkzeug.wrappers import Response

ENDPOINT = "/chat/completions"


def opencode_go_text_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def make_translator(httpserver: HTTPServer) -> OpencodeGoContentTranslator:
    return OpencodeGoContentTranslator(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )


def test_translate_returns_the_text_opencode_go_responds_with(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_text_response("  Nội dung đã dịch.\n")
    )

    result = make_translator(httpserver).translate("Original content.")

    assert result == "Nội dung đã dịch."


def test_translate_sends_the_content_in_the_prompt(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_text_response("x")
    )

    make_translator(httpserver).translate("Original content.")

    messages = httpserver.log[0][0].get_json()["messages"]
    assert "Original content." in messages[0]["content"]
    assert "Vietnamese" in messages[0]["content"]


def test_translate_truncates_content_beyond_the_limit(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_text_response("x")
    )
    content = "a" * MAX_CONTENT_CHARS + "TAIL"

    make_translator(httpserver).translate(content)

    prompt = httpserver.log[0][0].get_json()["messages"][0]["content"]
    assert "a" * MAX_CONTENT_CHARS in prompt
    assert "TAIL" not in prompt


def test_translate_raises_transformation_error_when_opencode_go_keeps_failing(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500, headers={"Retry-After": "0.01"})
    )

    with pytest.raises(TransformationError):
        make_translator(httpserver).translate("Original content.")


def test_translate_raises_transformation_error_on_an_empty_translation(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        opencode_go_text_response("   ")
    )

    with pytest.raises(TransformationError):
        make_translator(httpserver).translate("Original content.")
