import pytest
from smartnews_transformation.config import LlmStepConfig
from smartnews_transformation.filtering.factory import (
    build_content_translator,
    build_filter,
)
from smartnews_transformation.filtering.gemini import DEFAULT_MODEL, GeminiFilter
from smartnews_transformation.filtering.groq import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from smartnews_transformation.filtering.groq import GroqContentTranslator, GroqFilter
from smartnews_transformation.filtering.passthrough import PassthroughFilter


def test_build_filter_returns_passthrough_when_disabled() -> None:
    result = build_filter(LlmStepConfig(enabled=False))

    assert isinstance(result, PassthroughFilter)


def test_build_filter_builds_gemini_filter_from_env_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    result = build_filter(LlmStepConfig(enabled=True))

    assert isinstance(result, GeminiFilter)
    assert result._client._api_client.api_key == "fake-key"
    assert result._model == DEFAULT_MODEL


def test_build_filter_uses_configured_model_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    result = build_filter(LlmStepConfig(enabled=True, model="some-other-model"))

    assert isinstance(result, GeminiFilter)
    assert result._model == "some-other-model"


def test_build_filter_raises_when_enabled_but_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_filter(LlmStepConfig(enabled=True))


def test_build_filter_builds_groq_filter_from_env_when_provider_is_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    result = build_filter(LlmStepConfig(enabled=True, provider="groq"))

    assert isinstance(result, GroqFilter)
    assert result._client.api_key == "fake-key"
    assert result._model == GROQ_DEFAULT_MODEL


def test_build_filter_uses_configured_model_for_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    result = build_filter(
        LlmStepConfig(enabled=True, provider="groq", model="some-other-model")
    )

    assert isinstance(result, GroqFilter)
    assert result._model == "some-other-model"


def test_build_filter_raises_when_groq_enabled_but_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_filter(LlmStepConfig(enabled=True, provider="groq"))


def test_build_content_translator_returns_none_when_disabled() -> None:
    assert build_content_translator(LlmStepConfig(enabled=False)) is None


def test_build_content_translator_builds_groq_translator_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")

    result = build_content_translator(
        LlmStepConfig(enabled=True, provider="groq", model="some-other-model")
    )

    assert isinstance(result, GroqContentTranslator)
    assert result._client.api_key == "fake-key"
    assert result._model == "some-other-model"


def test_build_content_translator_raises_when_groq_env_var_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_content_translator(LlmStepConfig(enabled=True, provider="groq"))


def test_build_content_translator_rejects_providers_other_than_groq() -> None:
    with pytest.raises(RuntimeError, match="gemini"):
        build_content_translator(LlmStepConfig(enabled=True, provider="gemini"))
