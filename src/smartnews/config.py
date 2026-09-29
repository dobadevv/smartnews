from pathlib import Path

import yaml
from pydantic import BaseModel


class SourceConfig(BaseModel):
    name: str
    url: str
    enabled: bool = True
    max_posts: int | None = None
    lookback_days: int = 7


class NotifierConfig(BaseModel):
    enabled: bool = False


class NotifiersConfig(BaseModel):
    discord: NotifierConfig = NotifierConfig()
    telegram: NotifierConfig = NotifierConfig()


class FilterConfig(BaseModel):
    enabled: bool = False
    provider: str = "gemini"
    model: str | None = None


def load_sources(path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(path.read_text())
    return [SourceConfig(**item) for item in data["sources"]]


def load_notifiers(path: Path) -> NotifiersConfig:
    data = yaml.safe_load(path.read_text())
    return NotifiersConfig(**data.get("notifiers", {}))


def load_filter(path: Path) -> FilterConfig:
    data = yaml.safe_load(path.read_text())
    return FilterConfig(**data.get("filter", {}))
