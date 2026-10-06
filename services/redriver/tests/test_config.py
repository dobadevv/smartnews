from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_redriver.config import (
    RedriverConfig,
    RetransformConfig,
    load_redriver_config,
)

REPO_CONFIG = Path(__file__).resolve().parents[3] / "config" / "redriver.yaml"


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "redriver.yaml"
    path.write_text(content)
    return path


def test_load_redriver_config_parses_every_field(tmp_path: Path) -> None:
    path = write_config(
        tmp_path=tmp_path,
        content="""
timezone: Asia/Kolkata
run_once: true
delay_seconds: 2.5
max_messages_per_run: 25
queues:
  - articles.crawl
  - articles.fetched
retransform:
  enabled: false
  min_age_minutes: 15
""",
    )

    config = load_redriver_config(path)

    assert config == RedriverConfig(
        timezone="Asia/Kolkata",
        run_once=True,
        delay_seconds=2.5,
        max_messages_per_run=25,
        queues=["articles.crawl", "articles.fetched"],
        retransform=RetransformConfig(enabled=False, min_age_minutes=15),
    )


def test_redriver_config_defaults_to_hourly_crawl_redrive_in_ho_chi_minh() -> None:
    config = RedriverConfig()

    assert (
        config.timezone,
        config.run_once,
        config.delay_seconds,
        config.max_messages_per_run,
        config.queues,
    ) == (
        "Asia/Ho_Chi_Minh",
        False,
        5,
        10,
        ["articles.crawl"],
    )


def test_redriver_config_defaults_to_retransforming_articles_older_than_an_hour() -> None:
    config = RedriverConfig()

    assert config.retransform.enabled is True
    assert config.retransform.min_age_minutes == 60


def test_load_redriver_config_uses_the_retransform_defaults_when_the_section_is_missing(
    tmp_path: Path,
) -> None:
    config = load_redriver_config(
        write_config(tmp_path=tmp_path, content="run_once: true\n")
    )

    assert config.retransform == RetransformConfig(enabled=True, min_age_minutes=60)


def test_load_redriver_config_uses_the_defaults_for_an_empty_file(
    tmp_path: Path,
) -> None:
    config = load_redriver_config(write_config(tmp_path=tmp_path, content=""))

    assert config == RedriverConfig()


def test_redriver_config_accepts_an_empty_queue_list() -> None:
    assert RedriverConfig(queues=[]).queues == []


def test_redriver_config_accepts_a_zero_minimum_age_for_local_testing() -> None:
    config = RedriverConfig.model_validate({"retransform": {"min_age_minutes": 0}})

    assert config.retransform.min_age_minutes == 0


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"timezone": "Not/AZone"}, id="unknown-timezone"),
        pytest.param({"delay_seconds": -1}, id="negative-delay"),
        pytest.param({"max_messages_per_run": 0}, id="zero-message-limit"),
        pytest.param({"max_messages_per_run": -1}, id="negative-message-limit"),
        pytest.param(
            {"retransform": {"min_age_minutes": -1}}, id="negative-minimum-age"
        ),
    ],
)
def test_redriver_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RedriverConfig.model_validate(overrides)


def test_the_repository_redriver_config_loads() -> None:
    config = load_redriver_config(REPO_CONFIG)

    assert config.queues == ["articles.crawled"]
    assert config.run_once is False
    assert config.max_messages_per_run == 10
    assert config.retransform == RetransformConfig(enabled=True, min_age_minutes=60)
