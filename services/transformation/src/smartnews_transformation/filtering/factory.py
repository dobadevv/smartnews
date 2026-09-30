import os

from smartnews_transformation.config import FilterConfig
from smartnews_transformation.filtering.base import Filter
from smartnews_transformation.filtering.gemini import GeminiFilter
from smartnews_transformation.filtering.groq import GroqFilter
from smartnews_transformation.filtering.passthrough import PassthroughFilter


def build_filter(config: FilterConfig) -> Filter:
    if not config.enabled:
        return PassthroughFilter()

    if config.provider == "groq":
        return _build_groq_filter(config)
    return _build_gemini_filter(config)


def _build_gemini_filter(config: FilterConfig) -> GeminiFilter:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be set when the filter is enabled")
    if config.model:
        return GeminiFilter(api_key, model=config.model)
    return GeminiFilter(api_key)


def _build_groq_filter(config: FilterConfig) -> GroqFilter:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY must be set when the filter is enabled")
    if config.model:
        return GroqFilter(api_key, model=config.model)
    return GroqFilter(api_key)
