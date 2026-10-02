import pytest
from smartnews_notifier.config import NotifiersConfig
from smartnews_notifier.notifiers.discord import DiscordNotifier
from smartnews_notifier.notifiers.factory import build_notifiers
from smartnews_notifier.notifiers.telegram import TelegramNotifier


def test_build_notifiers_returns_empty_list_when_none_enabled() -> None:
    notifiers = build_notifiers(NotifiersConfig())

    assert notifiers == []


def test_build_notifiers_builds_discord_notifier_from_env_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webhook_url = f"https://discord.com/api/webhooks/123456789012345678/{'b' * 68}"
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook_url)
    config = NotifiersConfig(discord={"enabled": True})

    notifiers = build_notifiers(config)

    assert len(notifiers) == 1
    assert isinstance(notifiers[0], DiscordNotifier)
    assert notifiers[0]._webhook.url == webhook_url


def test_build_notifiers_raises_when_discord_enabled_but_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    config = NotifiersConfig(discord={"enabled": True})

    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        build_notifiers(config)


def test_build_notifiers_builds_telegram_notifier_from_env_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    config = NotifiersConfig(telegram={"enabled": True})

    notifiers = build_notifiers(config)

    assert len(notifiers) == 1
    assert isinstance(notifiers[0], TelegramNotifier)


def test_build_notifiers_raises_when_telegram_enabled_but_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    config = NotifiersConfig(telegram={"enabled": True})

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        build_notifiers(config)
