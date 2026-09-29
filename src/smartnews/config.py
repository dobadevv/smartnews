from datetime import time as time_of_day
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, field_validator


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


class CronjobConfig(BaseModel):
    enabled: bool = True
    time: str = "07:00"
    timezone: str = "Asia/Ho_Chi_Minh"

    @field_validator("time")
    @classmethod
    def _validate_time_format(cls, value: str) -> str:
        try:
            parsed = time_of_day.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"cronjob.time must be in HH:MM format, got {value!r}"
            ) from exc
        if value != parsed.strftime("%H:%M"):
            raise ValueError(f"cronjob.time must be in HH:MM format, got {value!r}")
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone_name(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(
                f"cronjob.timezone is not a valid IANA timezone name: {value!r}"
            ) from exc
        return value


def load_sources(path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(path.read_text())
    return [SourceConfig(**item) for item in data["sources"]]


def load_notifiers(path: Path) -> NotifiersConfig:
    data = yaml.safe_load(path.read_text())
    return NotifiersConfig(**data.get("notifiers", {}))


def load_filter(path: Path) -> FilterConfig:
    data = yaml.safe_load(path.read_text())
    return FilterConfig(**data.get("filter", {}))


def load_cronjob(path: Path) -> CronjobConfig:
    data = yaml.safe_load(path.read_text())
    return CronjobConfig(**data.get("cronjob", {}))
