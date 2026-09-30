from datetime import time
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
    category: str | None = None


class FetcherConfig(BaseModel):
    run_at: time = time(7, 0)
    timezone: str = "Asia/Ho_Chi_Minh"
    sources: list[SourceConfig]

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, timezone: str) -> str:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {timezone}") from error
        return timezone


def load_fetcher_config(path: Path) -> FetcherConfig:
    return FetcherConfig.model_validate(yaml.safe_load(path.read_text()))
