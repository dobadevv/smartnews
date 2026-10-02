import os

from smartnews_transformer.config import LlmStepConfig
from smartnews_transformer.filtering.base import ContentTranslator, Filter
from smartnews_transformer.filtering.gemini import (
    GeminiContentTranslator,
    GeminiFilter,
)
from smartnews_transformer.filtering.groq import GroqContentTranslator, GroqFilter
from smartnews_transformer.filtering.passthrough import PassthroughFilter


def build_filter(config: LlmStepConfig) -> Filter:
    if not config.enabled:
        return PassthroughFilter()

    match config.provider:
        case "gemini":
            return GeminiFilter(
                _require_api_key("GEMINI_API_KEY"), **_model_options(config)
            )
        case "groq":
            return GroqFilter(
                _require_api_key("GROQ_API_KEY"), **_model_options(config)
            )
        case _:
            raise _unsupported_provider(config)


def build_content_translator(config: LlmStepConfig) -> ContentTranslator | None:
    if not config.enabled:
        return None

    match config.provider:
        case "gemini":
            return GeminiContentTranslator(
                _require_api_key("GEMINI_API_KEY"), **_model_options(config)
            )
        case "groq":
            return GroqContentTranslator(
                _require_api_key("GROQ_API_KEY"), **_model_options(config)
            )
        case _:
            raise _unsupported_provider(config)


def _model_options(config: LlmStepConfig) -> dict[str, str]:
    return {"model": config.model} if config.model else {}


def _require_api_key(name: str) -> str:
    api_key = os.environ.get(name)
    if not api_key:
        raise RuntimeError(f"{name} must be set when its provider is enabled")
    return api_key


def _unsupported_provider(config: LlmStepConfig) -> RuntimeError:
    return RuntimeError(f"unsupported LLM provider: {config.provider!r}")
