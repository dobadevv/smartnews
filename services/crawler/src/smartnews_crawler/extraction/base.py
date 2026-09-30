from typing import Protocol


class ExtractionError(Exception):
    """The page's main content could not be extracted."""


class Extractor(Protocol):
    def extract(self, html: str, url: str) -> str:
        """Return the article's main text content.

        Raises ExtractionError when no usable content can be extracted.
        """
        ...
