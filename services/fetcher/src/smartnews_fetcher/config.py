from datetime import time
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator
from smartnews_common.timezones import validate_timezone


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
    run_once: bool = False
    sources: list[SourceConfig]

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, timezone: str) -> str:
        return validate_timezone(timezone)


def load_fetcher_config(path: Path) -> FetcherConfig:
    return FetcherConfig.model_validate(yaml.safe_load(path.read_text()))
