from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator

from smartnews_api.requests import PageSizeLimits


class ApiConfig(BaseModel):
    cors_allowed_origins: list[str] = []
    default_page_size: int = Field(default=20, ge=1)
    max_page_size: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def _default_within_maximum(self) -> Self:
        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size must not exceed max_page_size")
        return self

    @property
    def page_size_limits(self) -> PageSizeLimits:
        return PageSizeLimits(default=self.default_page_size, maximum=self.max_page_size)


def load_api_config(path: Path) -> ApiConfig:
    return ApiConfig.model_validate(yaml.safe_load(path.read_text()) or {})
