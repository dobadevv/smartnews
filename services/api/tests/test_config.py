from pathlib import Path

import pytest
from pydantic import ValidationError
from smartnews_api.config import load_api_config
from smartnews_api.requests import PageSizeLimits


def write_config(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "api.yaml"
    path.write_text(content)
    return path


def test_load_api_config_parses_every_setting(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        "cors_allowed_origins: ['https://reader.example']\ndefault_page_size: 10\nmax_page_size: 50\n",
    )

    config = load_api_config(path)

    assert config.cors_allowed_origins == ["https://reader.example"]
    assert config.page_size_limits == PageSizeLimits(default=10, maximum=50)


def test_load_api_config_defaults_when_the_file_is_empty(tmp_path: Path) -> None:
    config = load_api_config(write_config(tmp_path, ""))

    assert config.cors_allowed_origins == []
    assert config.page_size_limits == PageSizeLimits(default=20, maximum=100)


@pytest.mark.parametrize(
    "content",
    [
        "default_page_size: 0\n",
        "max_page_size: 0\n",
        "default_page_size: 60\nmax_page_size: 50\n",
    ],
    ids=["default below one", "maximum below one", "default above maximum"],
)
def test_load_api_config_rejects_inconsistent_page_sizes(tmp_path: Path, content: str) -> None:
    with pytest.raises(ValidationError):
        load_api_config(write_config(tmp_path, content))
