from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_redriver.config import RedriverConfig, load_redriver_config

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config" / "redriver.yaml"


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "redriver.yaml"
    path.write_text(content)
    return path


def test_load_redriver_config_parses_every_field(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        """
timezone: Asia/Kolkata
run_once: true
delay_seconds: 2.5
queues:
  - articles.crawl
  - articles.fetched
""",
    )

    config = load_redriver_config(path)

    assert config == RedriverConfig(
        timezone="Asia/Kolkata",
        run_once=True,
        delay_seconds=2.5,
        queues=["articles.crawl", "articles.fetched"],
    )


def test_redriver_config_defaults_to_hourly_crawl_redrive_in_ho_chi_minh() -> None:
    config = RedriverConfig()

    assert (config.timezone, config.run_once, config.delay_seconds, config.queues) == (
        "Asia/Ho_Chi_Minh",
        False,
        5,
        ["articles.crawl"],
    )


def test_load_redriver_config_uses_the_defaults_for_an_empty_file(
    tmp_path: Path,
) -> None:
    config = load_redriver_config(write_config(tmp_path, ""))

    assert config == RedriverConfig()


def test_redriver_config_accepts_an_empty_queue_list() -> None:
    assert RedriverConfig(queues=[]).queues == []


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"timezone": "Not/AZone"}, id="unknown-timezone"),
        pytest.param({"delay_seconds": -1}, id="negative-delay"),
    ],
)
def test_redriver_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RedriverConfig.model_validate(overrides)


def test_the_repository_redriver_config_loads() -> None:
    config = load_redriver_config(REPO_CONFIG)

    assert config.queues == ["articles.crawl"]
    assert config.run_once is False
