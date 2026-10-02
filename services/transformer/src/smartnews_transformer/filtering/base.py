from typing import Protocol

from smartnews_common.models import Article, Transformation


class TransformationError(Exception):
    """The LLM provider could not produce a transformation for an article."""


class Filter(Protocol):
    def transform(self, article: Article) -> Transformation | None:
        """Return the translated title/summary, or None to leave it untranslated.

        Raises TransformationError when the provider call fails.
        """
        ...


class ContentTranslator(Protocol):
    def translate(self, content: str) -> str:
        """Return the content translated into Vietnamese.

        Raises TransformationError when the provider call fails.
        """
        ...
