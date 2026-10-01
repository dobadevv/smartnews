import os

from smartnews_transformation.config import LlmStepConfig
from smartnews_transformation.filtering.base import ContentTranslator, Filter
from smartnews_transformation.filtering.gemini import GeminiFilter
from smartnews_transformation.filtering.groq import GroqContentTranslator, GroqFilter
from smartnews_transformation.filtering.passthrough import PassthroughFilter


def build_filter(config: LlmStepConfig) -> Filter:
    if not config.enabled:
        return PassthroughFilter()

    if config.provider == "groq":
        return _build_groq_filter(config)
    return _build_gemini_filter(config)


def build_content_translator(config: LlmStepConfig) -> ContentTranslator | None:
    if not config.enabled:
        return None

    if config.provider != "groq":
        raise RuntimeError(
            f"content translation only supports groq, not {config.provider}"
        )
    api_key = _require_groq_api_key()
    if config.model:
        return GroqContentTranslator(api_key, model=config.model)
    return GroqContentTranslator(api_key)


def _build_gemini_filter(config: LlmStepConfig) -> GeminiFilter:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be set when the filter is enabled")
    if config.model:
        return GeminiFilter(api_key, model=config.model)
    return GeminiFilter(api_key)


def _require_groq_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY must be set when the filter is enabled")
    return api_key


def _build_groq_filter(config: LlmStepConfig) -> GroqFilter:
    api_key = _require_groq_api_key()
    if config.model:
        return GroqFilter(api_key, model=config.model)
    return GroqFilter(api_key)
