import json
import logging
import time
from collections.abc import Mapping

from groq import APIStatusError, Groq
from groq.types.chat import ChatCompletion
from smartnews_common.models import Article, Transformation

from smartnews_transformation.filtering.base import TransformationError
from smartnews_transformation.filtering.prompts import (
    MAX_CONTENT_CHARS,
    build_content_translation_prompt,
    build_translation_prompt,
)

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


class _GroqModel:
    def __init__(
        self,
        api_key: str,
        model: str,
        api_base_url: str,
        rate_limit_timeout: float,
    ) -> None:
        self._model = model
        self._rate_limit_timeout = rate_limit_timeout
        self._client = Groq(api_key=api_key, base_url=api_base_url, max_retries=2)

    def _complete(self, prompt: str, **options) -> ChatCompletion:
        deadline = time.monotonic() + self._rate_limit_timeout
        while True:
            try:
                return self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=15,
                    **options,
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


class GroqFilter(_GroqModel):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
        rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(api_key, model, api_base_url, rate_limit_timeout)

    def transform(self, article: Article) -> Transformation:
        try:
            title, summary = self._request(article)
        except Exception as error:
            raise TransformationError(
                f"groq transformation failed for {article.url}"
            ) from error
        return Transformation(title=title, summary=summary, language="vi")

    def _request(self, article: Article) -> tuple[str, str]:
        response = self._complete(
            build_translation_prompt(article),
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)
        return parsed["title"], parsed["summary"]


class GroqContentTranslator(_GroqModel):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
        rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(api_key, model, api_base_url, rate_limit_timeout)

    def translate(self, content: str) -> str:
        try:
            response = self._complete(
                build_content_translation_prompt(content[:MAX_CONTENT_CHARS])
            )
            translated = response.choices[0].message.content.strip()
        except Exception as error:
            raise TransformationError("groq content translation failed") from error
        if not translated:
            raise TransformationError("groq returned an empty content translation")
        return translated
