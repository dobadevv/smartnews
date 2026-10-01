import logging

import pytest
from pytest_httpserver import HTTPServer
from smartnews_transformation.filtering.base import TransformationError
from smartnews_transformation.filtering.gemini import GeminiContentTranslator
from smartnews_transformation.filtering.prompts import MAX_CONTENT_CHARS
from werkzeug.wrappers import Response

ENDPOINT = "/v1beta/models/gemini-3.8-flash:generateContent"


def gemini_text_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def make_translator(httpserver: HTTPServer) -> GeminiContentTranslator:
    return GeminiContentTranslator(
        api_key="fake-key", api_base_url=httpserver.url_for("")
    )


def prompt_sent(httpserver: HTTPServer) -> str:
    return httpserver.log[0][0].get_json()["contents"][0]["parts"][0]["text"]


def test_translate_returns_the_text_gemini_responds_with(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_text_response("  Nội dung đã dịch.\n")
    )

    result = make_translator(httpserver).translate("Original content.")

    assert result == "Nội dung đã dịch."


def test_translate_sends_the_content_in_the_prompt(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_text_response("x")
    )

    make_translator(httpserver).translate("Original content.")

    prompt = prompt_sent(httpserver)
    assert "Original content." in prompt
    assert "Vietnamese" in prompt


def test_translate_asks_for_plain_text_not_json(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_text_response("x")
    )

    make_translator(httpserver).translate("Original content.")

    generation_config = httpserver.log[0][0].get_json().get("generationConfig", {})
    assert "responseMimeType" not in generation_config
    assert "responseSchema" not in generation_config


def test_translate_truncates_content_beyond_the_limit(httpserver: HTTPServer) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(
        gemini_text_response("x")
    )
    content = "a" * MAX_CONTENT_CHARS + "TAIL"

    make_translator(httpserver).translate(content)

    prompt = prompt_sent(httpserver)
    assert "a" * MAX_CONTENT_CHARS in prompt
    assert "TAIL" not in prompt


@pytest.mark.parametrize("status", [429, 500, 503])
def test_translate_raises_transformation_error_when_the_request_fails(
    httpserver: HTTPServer, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=status)
    )

    with caplog.at_level(logging.ERROR), pytest.raises(TransformationError):
        make_translator(httpserver).translate("Original content.")

    messages = [record.getMessage() for record in caplog.records]
    assert any(str(status) in message for message in messages)
    assert not any("fake-key" in message for message in messages)


@pytest.mark.parametrize(
    "response_body",
    [
        {"candidates": []},
        {"promptFeedback": {"blockReason": "SAFETY"}},
        gemini_text_response("   "),
    ],
    ids=["no-candidates", "prompt-blocked", "blank-text"],
)
def test_translate_raises_transformation_error_when_gemini_returns_no_text(
    httpserver: HTTPServer, response_body: dict
) -> None:
    httpserver.expect_request(ENDPOINT, method="POST").respond_with_json(response_body)

    with pytest.raises(TransformationError):
        make_translator(httpserver).translate("Original content.")


def test_translate_next_call_succeeds_after_a_previous_call_failed(
    httpserver: HTTPServer,
) -> None:
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_response(
        Response(status=500)
    )
    httpserver.expect_ordered_request(ENDPOINT, method="POST").respond_with_json(
        gemini_text_response("Đã dịch")
    )
    translator = make_translator(httpserver)

    with pytest.raises(TransformationError):
        translator.translate("first")

    assert translator.translate("second") == "Đã dịch"
