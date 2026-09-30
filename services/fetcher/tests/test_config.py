from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_fetcher.config import FetcherConfig, SourceConfig, load_fetcher_config


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "fetcher.yaml"
    path.write_text(content)
    return path


def test_load_fetcher_config_parses_interval_and_every_source_field(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
fetch_interval_minutes: 30
sources:
  - name: hacker-news
    url: https://hnrss.org/frontpage
    category: architecture
    enabled: false
    max_posts: 2
    lookback_days: 3
""",
    )

    config = load_fetcher_config(path)

    assert config.fetch_interval == timedelta(minutes=30)
    assert config.sources == [
        SourceConfig(
            name="hacker-news",
            url="https://hnrss.org/frontpage",
            category="architecture",
            enabled=False,
            max_posts=2,
            lookback_days=3,
        )
    ]


def test_source_config_defaults() -> None:
    source = SourceConfig(name="s", url="https://a")

    assert (source.enabled, source.max_posts, source.lookback_days, source.category) == (
        True, None, 7, None
    )


@pytest.mark.parametrize(
    "interval",
    [pytest.param(0, id="zero"), pytest.param(-5, id="negative")],
)
def test_fetcher_config_rejects_a_non_positive_interval(interval: int) -> None:
    with pytest.raises(ValidationError):
        FetcherConfig(fetch_interval_minutes=interval, sources=[])


def test_fetcher_config_requires_an_interval() -> None:
    with pytest.raises(ValidationError):
        FetcherConfig.model_validate({"sources": []})
