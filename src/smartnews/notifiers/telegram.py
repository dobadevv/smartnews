import html
import logging

import requests

from smartnews.models import Article

DEFAULT_API_BASE_URL = "https://api.telegram.org/"

MESSAGE_TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024

_TRUNCATION_MARKER = "…"

logger = logging.getLogger(__name__)


class TelegramNotifier:
    channel = "telegram"

    def __init__(
        self, bot_token: str, chat_id: str, api_base_url: str = DEFAULT_API_BASE_URL
    ) -> None:
        self._bot_url = f"{api_base_url.rstrip('/')}/bot{bot_token}"
        self._chat_id = chat_id

    def send(self, article: Article) -> None:
        if article.thumbnail:
            endpoint = "sendPhoto"
            payload = {
                "chat_id": self._chat_id,
                "photo": article.thumbnail,
                "caption": self._build_caption(article, max_length=CAPTION_LIMIT),
                "parse_mode": "HTML",
            }
        else:
            endpoint = "sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": self._build_caption(article, max_length=MESSAGE_TEXT_LIMIT),
                "parse_mode": "HTML",
            }

        response = requests.post(
            f"{self._bot_url}/{endpoint}", json=payload, timeout=10
        )
        if not response.ok:
            logger.error(
                "telegram %s failed: status=%d payload=%s response=%s",
                endpoint,
                response.status_code,
                payload,
                response.text,
            )
        response.raise_for_status()

    @staticmethod
    def _build_caption(article: Article, *, max_length: int) -> str:
        title_with_category = (
            f"[{article.category}] {article.title}"
            if article.category
            else article.title
        )
        header = f"🔥🔥 {title_with_category} 🔥🔥"
        footer = "\n\n🔗 " + article.url

        summary = article.summary
        if summary:
            budget = max_length - len(header) - len(footer) - len("\n\n")
            if len(summary) > budget:
                truncated_length = max(budget - len(_TRUNCATION_MARKER), 0)
                summary = summary[:truncated_length].rstrip() + _TRUNCATION_MARKER

        header_html = f"<b>{html.escape(header, quote=False)}</b>"
        url_html = "🔗 " + html.escape(article.url, quote=False)

        if summary:
            summary_html = (
                f"<blockquote>{html.escape(summary, quote=False)}</blockquote>"
            )
            return f"{header_html}\n\n{summary_html}\n\n{url_html}"
        return f"{header_html}\n\n{url_html}"
