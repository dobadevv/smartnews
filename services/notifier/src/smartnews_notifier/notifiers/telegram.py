import asyncio
import html
import logging

from smartnews_common.models import Article
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

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
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"{api_base_url.rstrip('/')}/bot"

    def send(self, article: Article) -> None:
        asyncio.run(self._send_async(article))

    async def _send_async(self, article: Article) -> None:
        async with Bot(token=self._bot_token, base_url=self._base_url) as bot:
            if article.thumbnail:
                await self._send_photo(bot, article)
            else:
                await self._send_message(bot, article)

    async def _send_photo(self, bot: Bot, article: Article) -> None:
        caption = self._build_caption(article, max_length=CAPTION_LIMIT)
        try:
            await bot.send_photo(
                chat_id=self._chat_id,
                photo=article.thumbnail,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        except TelegramError as exc:
            logger.error(
                "telegram sendPhoto failed: payload=%s response=%s", caption, exc
            )
            raise

    async def _send_message(self, bot: Bot, article: Article) -> None:
        text = self._build_caption(article, max_length=MESSAGE_TEXT_LIMIT)
        try:
            await bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode=ParseMode.HTML
            )
        except TelegramError as exc:
            logger.error(
                "telegram sendMessage failed: payload=%s response=%s", text, exc
            )
            raise

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
