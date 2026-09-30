from typing import Protocol


class FetchError(Exception):
    """The page could not be downloaded (network error, timeout, non-2xx status)."""


class PageFetcher(Protocol):
    def fetch(self, url: str) -> bytes:
        """Return the page's raw HTML bytes.

        Returned as bytes, not decoded text, so extraction can sniff the
        page's own declared encoding (e.g. <meta charset>) instead of
        relying on the HTTP response's charset guess, which defaults to
        ISO-8859-1 when the server doesn't declare one.

        Raises FetchError when the page cannot be downloaded.
        """
        ...
