from datetime import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_fetcher.config import FetcherConfig, SourceConfig, load_fetcher_config


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "fetcher.yaml"
    path.write_text(content)
    return path


def test_load_fetcher_config_parses_run_at_timezone_and_every_source_field(
    tmp_path: Path,
) -> None:
    path = write_config(
        tmp_path,
        """
run_at: "08:30"
timezone: America/New_York
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

    assert (config.run_at, config.timezone) == (time(8, 30), "America/New_York")
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

    assert (
        source.enabled,
        source.max_posts,
        source.lookback_days,
        source.category,
    ) == (True, None, 7, None)


def test_fetcher_config_defaults_to_seven_am_asia_ho_chi_minh() -> None:
    config = FetcherConfig(sources=[])

    assert (config.run_at, config.timezone) == (time(7, 0), "Asia/Ho_Chi_Minh")


def test_fetcher_config_rejects_an_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        FetcherConfig(timezone="Not/AZone", sources=[])
