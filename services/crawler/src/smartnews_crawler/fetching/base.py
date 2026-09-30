from typing import Protocol


class FetchError(Exception):
    """The page could not be downloaded (network error, timeout, non-2xx status)."""


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str:
        """Return the page's HTML.

        Raises FetchError when the page cannot be downloaded.
        """
        ...
