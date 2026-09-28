import logging

import requests

from smartnews.models import Article

TITLE_LIMIT = 256
DESCRIPTION_LIMIT = 4096

_CODE_FENCE = "```"
_TRUNCATION_MARKER = "…"
_MARKDOWN_SPECIAL_CHARS = ("\\", "*", "_", "~", "`", "|", ">")

logger = logging.getLogger(__name__)


class DiscordNotifier:
    channel = "discord"

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send(self, articles: list[Article]) -> None:
        for article in articles:
            payload = {"embeds": [self._build_embed(article)]}
            response = requests.post(self._webhook_url, json=payload, timeout=10)
            if not response.ok:
                logger.error(
                    "discord webhook failed: status=%d payload=%s response=%s",
                    response.status_code,
                    payload,
                    response.text,
                )
            response.raise_for_status()

    @staticmethod
    def _build_embed(article: Article) -> dict[str, object]:
        title_with_category = (
            f"[{article.category}] {article.title}"
            if article.category
            else article.title
        )
        header = _escape_markdown(f"🔥🔥 {title_with_category} 🔥🔥")

        embed: dict[str, object] = {
            "title": _truncate(header, TITLE_LIMIT),
            "url": article.url,
        }

        if article.summary:
            budget = DESCRIPTION_LIMIT - 2 * len(_CODE_FENCE)
            summary = _escape_code_fence(_truncate(article.summary, budget))
            embed["description"] = f"{_CODE_FENCE}{summary}{_CODE_FENCE}"

        if article.thumbnail:
            embed["image"] = {"url": article.thumbnail}

        return embed


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    truncated_length = max(max_length - len(_TRUNCATION_MARKER), 0)
    return text[:truncated_length].rstrip() + _TRUNCATION_MARKER


def _escape_markdown(text: str) -> str:
    for char in _MARKDOWN_SPECIAL_CHARS:
        text = text.replace(char, "\\" + char)
    return text


def _escape_code_fence(text: str) -> str:
    return text.replace(_CODE_FENCE, "`\u200b``")
