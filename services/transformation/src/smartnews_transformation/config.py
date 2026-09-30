from pathlib import Path

import yaml
from pydantic import BaseModel


class FilterConfig(BaseModel):
    enabled: bool = False
    provider: str = "gemini"
    model: str | None = None


class TransformationConfig(BaseModel):
    filter: FilterConfig = FilterConfig()


def load_transformation_config(path: Path) -> TransformationConfig:
    return TransformationConfig.model_validate(yaml.safe_load(path.read_text()) or {})
