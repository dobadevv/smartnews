from pathlib import Path

import yaml
from pydantic import BaseModel


class NotifierConfig(BaseModel):
    enabled: bool = False


class NotifiersConfig(BaseModel):
    discord: NotifierConfig = NotifierConfig()
    telegram: NotifierConfig = NotifierConfig()


class NotificationConfig(BaseModel):
    notifiers: NotifiersConfig = NotifiersConfig()


def load_notification_config(path: Path) -> NotificationConfig:
    return NotificationConfig.model_validate(yaml.safe_load(path.read_text()) or {})
