from pathlib import Path

from smartnews_notification.config import load_notification_config


def test_load_notification_config_parses_enabled_flag_per_channel(tmp_path: Path) -> None:
    path = tmp_path / "notification.yaml"
    path.write_text("notifiers:\n  discord:\n    enabled: true\n  telegram:\n    enabled: false\n")

    config = load_notification_config(path)

    assert (config.notifiers.discord.enabled, config.notifiers.telegram.enabled) == (True, False)


def test_load_notification_config_defaults_to_all_channels_disabled(tmp_path: Path) -> None:
    path = tmp_path / "notification.yaml"
    path.write_text("")

    config = load_notification_config(path)

    assert (config.notifiers.discord.enabled, config.notifiers.telegram.enabled) == (False, False)
