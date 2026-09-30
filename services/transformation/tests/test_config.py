from pathlib import Path

from smartnews_transformation.config import FilterConfig, load_transformation_config


def test_load_transformation_config_parses_the_filter_section(tmp_path: Path) -> None:
    path = tmp_path / "transformation.yaml"
    path.write_text("filter:\n  enabled: true\n  provider: groq\n  model: openai/gpt-oss-120b\n")

    config = load_transformation_config(path)

    assert config.filter == FilterConfig(enabled=True, provider="groq", model="openai/gpt-oss-120b")


def test_load_transformation_config_defaults_to_a_disabled_filter(tmp_path: Path) -> None:
    path = tmp_path / "transformation.yaml"
    path.write_text("")

    config = load_transformation_config(path)

    assert config.filter == FilterConfig(enabled=False, provider="gemini", model=None)
