import json
import logging
import time
import uuid

from openai import APIStatusError, OpenAI, RateLimitError
from openai.types.chat import ChatCompletion
from smartnews_common.models import Article, Transformation

from smartnews_transformer.filtering.base import TransformationError
from smartnews_transformer.filtering.prompts import (
    MAX_CONTENT_CHARS,
    build_content_translation_prompt,
    build_translation_prompt,
)

DEFAULT_API_BASE_URL = "https://opencode.ai/zen/go/v1"
DEFAULT_MODEL = "mimo-v2.6-flash"
REQUEST_TIMEOUT_SECONDS = 30
MAX_RATE_LIMIT_RETRIES = 3
BASE_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 80
# MiMo-V2.6-Flash pricing on OpenCode Go ($0.14/M input, $0.28/M output)
MODEL_INPUT_PRICE_PER_MILLION = 0.14
MODEL_OUTPUT_PRICE_PER_MILLION = 0.28
# OpenCode Go asks every client to identify itself instead of sending the
# SDK's generic user agent.
USER_AGENT = "smartnews-transformer/1.0"
SESSION_HEADER = "x-opencode-session"

logger = logging.getLogger(__name__)


def _message_content(response: ChatCompletion) -> str:
    if not response.choices:
        raise TransformationError("opencode-go returned no choices")
    content = response.choices[0].message.content
    if content is None:
        raise TransformationError("opencode-go returned no message content")
    return content


class _OpencodeGoModel:
    def __init__(self, api_key: str, model: str, api_base_url: str) -> None:
        self._model = model
        # OpenCode Go routes and caches prompts per session, so one process
        # keeps a single session ID for all its requests.
        self._client = OpenAI(
            api_key=api_key,
            base_url=api_base_url,
            max_retries=2,
            default_headers={
                "User-Agent": USER_AGENT,
                SESSION_HEADER: str(uuid.uuid4()),
            },
        )

    def _complete(self, prompt: str, **options) -> ChatCompletion:
        last_rate_limit_error = None
        for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    **options,
                )
                self._log_usage(response)
                return response
            except RateLimitError as error:
                retry_after = self._retry_after_seconds(error, attempt)
                logger.warning(
                    "opencode-go rate limited (attempt %d/%d): retrying after %ds",
                    attempt, MAX_RATE_LIMIT_RETRIES, retry_after,
                )
                last_rate_limit_error = error
                time.sleep(retry_after)
            except APIStatusError as error:
                logger.error(
                    "opencode-go request failed: status=%d response=%s",
                    error.status_code,
                    error.response.text,
                )
                raise
        raise last_rate_limit_error

    @staticmethod
    def _retry_after_seconds(error: RateLimitError, attempt: int) -> int:
        header = error.response.headers.get("Retry-After") if error.response else None
        if header:
            try:
                return max(int(header), 1)
            except ValueError:
                pass
        # Exponential backoff: 5s, 10s, 20s, 40s, 80s
        return min(BASE_RETRY_SECONDS * (2 ** (attempt - 1)), MAX_RETRY_SECONDS)

    def _log_usage(self, response: ChatCompletion) -> None:
        usage = response.usage
        if usage is None:
            return
        input_cost = usage.prompt_tokens * MODEL_INPUT_PRICE_PER_MILLION
        output_cost = usage.completion_tokens * MODEL_OUTPUT_PRICE_PER_MILLION
        logger.info(
            "opencode-go usage: model=%s prompt_tokens=%d completion_tokens=%d "
            "total_tokens=%d estimated_cost=$%.6f",
            self._model,
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.total_tokens,
            input_cost + output_cost,
        )


class OpencodeGoFilter(_OpencodeGoModel):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        super().__init__(api_key, model, api_base_url)

    def transform(self, article: Article) -> Transformation:
        try:
            title, summary = self._request(article)
        except Exception as error:
            raise TransformationError(
                f"opencode-go transformation failed for {article.url}"
            ) from error
        return Transformation(title=title, summary=summary, language="vi")

    def _request(self, article: Article) -> tuple[str, str]:
        response = self._complete(
            build_translation_prompt(article),
            response_format={"type": "json_object"},
        )
        parsed = json.loads(_message_content(response))
        return parsed["title"], parsed["summary"]


class OpencodeGoContentTranslator(_OpencodeGoModel):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        super().__init__(api_key, model, api_base_url)

    def translate(self, content: str) -> str:
        try:
            response = self._complete(
                build_content_translation_prompt(content[:MAX_CONTENT_CHARS])
            )
            translated = _message_content(response).strip()
        except Exception as error:
            raise TransformationError(
                "opencode-go content translation failed"
            ) from error
        if not translated:
            raise TransformationError(
                "opencode-go returned an empty content translation"
            )
        return translated
