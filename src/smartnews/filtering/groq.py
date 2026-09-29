import dataclasses
import json
import logging

from groq import APIStatusError, Groq

from smartnews.filtering.prompts import build_translation_prompt
from smartnews.models import Article

DEFAULT_API_BASE_URL = "https://api.groq.com/"
DEFAULT_MODEL = "openai/gpt-oss-120b"

logger = logging.getLogger(__name__)


class GroqFilter:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        self._model = model
        self._client = Groq(api_key=api_key, base_url=api_base_url, max_retries=2)

    def filter(self, article: Article) -> Article:
        try:
            title, summary = self._request(article)
        except Exception:
            logger.exception("groq summarization failed for %s", article.url)
            return article
        return dataclasses.replace(article, title=title, summary=summary)

    def _request(self, article: Article) -> tuple[str, str]:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": build_translation_prompt(article)}
                ],
                response_format={"type": "json_object"},
                timeout=15,
            )
        except APIStatusError as error:
            logger.error(
                "groq request failed: status=%d response=%s",
                error.status_code,
                error.response.text,
            )
            raise

        text = response.choices[0].message.content
        parsed = json.loads(text)
        return parsed["title"], parsed["summary"]
