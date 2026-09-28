import os

from smartnews.config import NotifiersConfig
from smartnews.notifiers.base import Notifier
from smartnews.notifiers.discord import DiscordNotifier
from smartnews.notifiers.telegram import TelegramNotifier


def _require_env(name: str, *, enabled_for: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} must be set when the {enabled_for} notifier is enabled"
        )
    return value


def build_notifiers(config: NotifiersConfig) -> list[Notifier]:
    notifiers: list[Notifier] = []

    if config.discord.enabled:
        webhook_url = _require_env("DISCORD_WEBHOOK_URL", enabled_for="discord")
        notifiers.append(DiscordNotifier(webhook_url))

    if config.telegram.enabled:
        bot_token = _require_env("TELEGRAM_BOT_TOKEN", enabled_for="telegram")
        chat_id = _require_env("TELEGRAM_CHAT_ID", enabled_for="telegram")
        notifiers.append(TelegramNotifier(bot_token, chat_id))

    return notifiers
