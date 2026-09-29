import dataclasses
import json
import logging

import requests

from smartnews.filtering.prompts import build_translation_prompt
from smartnews.models import Article

DEFAULT_API_BASE_URL = "https://generativelanguage.googleapis.com/"
DEFAULT_MODEL = "gemini-3.8-flash"

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "summary": {"type": "STRING"},
    },
    "required": ["title", "summary"],
}

logger = logging.getLogger(__name__)


class GeminiFilter:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._url = f"{api_base_url.rstrip('/')}/v1beta/models/{model}:generateContent"

    def filter(self, article: Article) -> Article:
        try:
            title, summary = self._request(article)
        except Exception:
            logger.exception("gemini summarization failed for %s", article.url)
            return article
        return dataclasses.replace(article, title=title, summary=summary)

    def _request(self, article: Article) -> tuple[str, str]:
        payload = {
            "contents": [{"parts": [{"text": build_translation_prompt(article)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
            },
        }
        response = requests.post(
            self._url,
            headers={"x-goog-api-key": self._api_key},
            json=payload,
            timeout=15,
        )
        if not response.ok:
            logger.error(
                "gemini request failed: status=%d payload=%s response=%s",
                response.status_code,
                payload,
                response.text,
            )
        response.raise_for_status()

        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        return parsed["title"], parsed["summary"]
