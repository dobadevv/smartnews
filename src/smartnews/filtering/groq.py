import dataclasses
import json
import logging
import time
from collections.abc import Mapping

from groq import APIStatusError, Groq
from groq.types.chat import ChatCompletion

from smartnews.filtering.prompts import build_translation_prompt
from smartnews.models import Article

DEFAULT_API_BASE_URL = "https://api.groq.com/"
DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_RATE_LIMIT_TIMEOUT_SECONDS = 60.0
DEFAULT_RETRY_AFTER_SECONDS = 1.0
RATE_LIMIT_STATUS_CODE = 429

logger = logging.getLogger(__name__)


def _parse_retry_after(headers: Mapping[str, str]) -> float:
    value = headers.get("Retry-After")
    if value is None:
        return DEFAULT_RETRY_AFTER_SECONDS
    try:
        return max(0.0, float(value))
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS


class GroqFilter:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
        rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._rate_limit_timeout = rate_limit_timeout
        self._client = Groq(api_key=api_key, base_url=api_base_url, max_retries=2)

    def filter(self, article: Article) -> Article:
        try:
            title, summary = self._request(article)
        except Exception:
            logger.exception("groq summarization failed for %s", article.url)
            return article
        return dataclasses.replace(article, title=title, summary=summary)

    def _request(self, article: Article) -> tuple[str, str]:
        response = self._request_waiting_out_rate_limits(article)
        text = response.choices[0].message.content
        parsed = json.loads(text)
        return parsed["title"], parsed["summary"]

    def _request_waiting_out_rate_limits(self, article: Article) -> ChatCompletion:
        deadline = time.monotonic() + self._rate_limit_timeout
        while True:
            try:
                return self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "user", "content": build_translation_prompt(article)}
                    ],
                    response_format={"type": "json_object"},
                    timeout=15,
                )
            except APIStatusError as error:
                remaining = deadline - time.monotonic()
                if error.status_code == RATE_LIMIT_STATUS_CODE and remaining > 0:
                    retry_after = _parse_retry_after(error.response.headers)
                    time.sleep(min(retry_after, remaining))
                    continue
                logger.error(
                    "groq request failed: status=%d response=%s",
                    error.status_code,
                    error.response.text,
                )
                raise
