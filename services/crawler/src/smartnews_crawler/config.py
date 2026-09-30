from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; SmartNewsBot/1.0; +https://github.com/dobadev/smartnews)"


class ContentSelectorOverride(BaseModel):
    content_selector: str


class CrawlerConfig(BaseModel):
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    user_agent: str = DEFAULT_USER_AGENT
    overrides: dict[str, ContentSelectorOverride] = {}


def load_crawler_config(path: Path) -> CrawlerConfig:
    return CrawlerConfig.model_validate(yaml.safe_load(path.read_text()) or {})
