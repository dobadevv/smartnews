from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator
from smartnews_common.messaging.topology import ARTICLES_TO_CRAWL
from smartnews_common.timezones import validate_timezone


class RetransformConfig(BaseModel):
    enabled: bool = True
    # 0 republishes everything untranslated right away (local testing); the
    # default leaves articles still in the transformer's retry ladder alone.
    min_age_minutes: int = Field(default=60, ge=0)


class RedriverConfig(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    run_once: bool = False
    # Stay well below HEARTBEAT_SECONDS (600): the connection idles while waiting.
    delay_seconds: float = Field(default=5, ge=0)
    max_messages_per_run: int = Field(default=10, ge=1)
    queues: list[str] = [ARTICLES_TO_CRAWL]
    retransform: RetransformConfig = RetransformConfig()

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, timezone: str) -> str:
        return validate_timezone(timezone)


def load_redriver_config(path: Path) -> RedriverConfig:
    return RedriverConfig.model_validate(yaml.safe_load(path.read_text()) or {})
