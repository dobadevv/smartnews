import requests

from smartnews_crawler.config import DEFAULT_TIMEOUT_SECONDS, DEFAULT_USER_AGENT
from smartnews_crawler.fetching.base import FetchError


class HttpPageFetcher:
    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._headers = {"User-Agent": user_agent}

    def fetch(self, url: str) -> str:
        try:
            response = requests.get(url, headers=self._headers, timeout=self._timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as error:
            raise FetchError(f"failed to fetch {url}") from error
        return response.text
