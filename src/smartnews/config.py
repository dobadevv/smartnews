from pathlib import Path

import yaml
from pydantic import BaseModel


class SourceConfig(BaseModel):
    name: str
    url: str
    enabled: bool = True


def load_sources(path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(path.read_text())
    return [SourceConfig(**item) for item in data["sources"]]
