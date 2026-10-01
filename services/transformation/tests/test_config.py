from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_transformation.config import LlmStepConfig, load_transformation_config


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "transformation.yaml"
    path.write_text(text)
    return path


def test_load_transformation_config_parses_the_summary_and_content_sections(
    tmp_path: Path,
) -> None:
    path = write_config(
        tmp_path,
        "summary:\n  enabled: true\n  provider: gemini\n  model: gemini-3.8-flash\n"
        "content:\n  enabled: true\n  provider: groq\n  model: openai/gpt-oss-120b\n",
    )

    config = load_transformation_config(path)

    assert config.summary == LlmStepConfig(
        enabled=True, provider="gemini", model="gemini-3.8-flash"
    )
    assert config.content == LlmStepConfig(
        enabled=True, provider="groq", model="openai/gpt-oss-120b"
    )


def test_load_transformation_config_defaults_both_steps_to_disabled(
    tmp_path: Path,
) -> None:
    config = load_transformation_config(write_config(tmp_path, ""))

    disabled = LlmStepConfig(enabled=False, provider="gemini", model=None)
    assert config.summary == disabled
    assert config.content == disabled


def test_load_transformation_config_configures_each_step_independently(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path, "content:\n  enabled: true\n  provider: groq\n")

    config = load_transformation_config(path)

    assert config.summary.enabled is False
    assert config.content == LlmStepConfig(enabled=True, provider="groq", model=None)


def test_load_transformation_config_rejects_the_legacy_filter_section(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path, "filter:\n  enabled: true\n  provider: groq\n")

    with pytest.raises(ValidationError, match="filter"):
        load_transformation_config(path)


def test_load_transformation_config_rejects_a_misspelled_step_option(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path, "summary:\n  enabled: true\n  provder: groq\n")

    with pytest.raises(ValidationError, match="provder"):
        load_transformation_config(path)
