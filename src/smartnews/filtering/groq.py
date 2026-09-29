import dataclasses
import json
import logging

import requests

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
        self._api_key = api_key
        self._model = model
        self._url = f"{api_base_url.rstrip('/')}/openai/v1/chat/completions"

    def filter(self, articles: list[Article]) -> list[Article]:
        return [self._translate_and_brief(article) for article in articles]

    def _translate_and_brief(self, article: Article) -> Article:
        try:
            title, summary = self._request(article)
        except Exception:
            logger.exception("groq summarization failed for %s", article.url)
            return article
        return dataclasses.replace(article, title=title, summary=summary)

    def _request(self, article: Article) -> tuple[str, str]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": build_translation_prompt(article)}
            ],
            "response_format": {"type": "json_object"},
        }
        response = requests.post(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
            timeout=15,
        )
        if not response.ok:
            logger.error(
                "groq request failed: status=%d payload=%s response=%s",
                response.status_code,
                payload,
                response.text,
            )
        response.raise_for_status()

        text = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(text)
        return parsed["title"], parsed["summary"]
