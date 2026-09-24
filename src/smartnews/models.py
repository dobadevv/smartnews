from dataclasses import dataclass


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    source: str
    published_at: str | None
    summary: str | None
