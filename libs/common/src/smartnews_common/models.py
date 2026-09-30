from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Language = Literal["vi"]


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: datetime | None
    summary: str | None
    thumbnail: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class Transformation:
    title: str
    summary: str | None
    language: Language
