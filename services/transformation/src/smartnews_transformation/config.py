from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class LlmStepConfig(BaseModel):
    # Forbid unknown keys so a stale or misspelled option fails at startup
    # instead of silently disabling translation.
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "gemini"
    model: str | None = None


class TransformationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: LlmStepConfig = LlmStepConfig()
    content: LlmStepConfig = LlmStepConfig()


def load_transformation_config(path: Path) -> TransformationConfig:
    return TransformationConfig.model_validate(yaml.safe_load(path.read_text()) or {})
