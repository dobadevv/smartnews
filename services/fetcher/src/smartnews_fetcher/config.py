from datetime import timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    name: str
    url: str
    enabled: bool = True
    max_posts: int | None = None
    lookback_days: int = 7
    category: str | None = None


class FetcherConfig(BaseModel):
    fetch_interval_minutes: int = Field(gt=0)
    sources: list[SourceConfig]

    @property
    def fetch_interval(self) -> timedelta:
        return timedelta(minutes=self.fetch_interval_minutes)


def load_fetcher_config(path: Path) -> FetcherConfig:
    return FetcherConfig.model_validate(yaml.safe_load(path.read_text()))
