from pathlib import Path

import pytest
from pydantic import ValidationError

from smartnews.config import load_cronjob, load_filter, load_notifiers, load_sources


def write_sources_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(content)
    return path


def test_load_sources_parses_name_url_and_enabled(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
            enabled: true
          - name: another-source
            url: https://another.example.com/rss
            enabled: false
        """,
    )

    sources = load_sources(path)

    assert [s.name for s in sources] == ["example-blog", "another-source"]
    assert [s.url for s in sources] == [
        "https://example.com/feed.xml",
        "https://another.example.com/rss",
    ]
    assert [s.enabled for s in sources] == [True, False]


def test_load_sources_defaults_enabled_to_true_when_omitted(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
        """,
    )

    sources = load_sources(path)

    assert sources[0].enabled is True


def test_load_sources_parses_max_posts_when_provided(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
            max_posts: 3
        """,
    )

    sources = load_sources(path)

    assert sources[0].max_posts == 3


def test_load_sources_defaults_max_posts_to_none_when_omitted(
    tmp_path: Path,
) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
        """,
    )

    sources = load_sources(path)

    assert sources[0].max_posts is None


def test_load_sources_parses_lookback_days_when_provided(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
            lookback_days: 3
        """,
    )

    sources = load_sources(path)

    assert sources[0].lookback_days == 3


def test_load_sources_defaults_lookback_days_to_seven_when_omitted(
    tmp_path: Path,
) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources:
          - name: example-blog
            url: https://example.com/feed.xml
        """,
    )

    sources = load_sources(path)

    assert sources[0].lookback_days == 7


def test_load_notifiers_parses_enabled_flag_per_channel(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        notifiers:
          discord:
            enabled: true
          telegram:
            enabled: false
        """,
    )

    notifiers = load_notifiers(path)

    assert notifiers.discord.enabled is True
    assert notifiers.telegram.enabled is False


def test_load_notifiers_defaults_to_all_disabled_when_section_missing(
    tmp_path: Path,
) -> None:
    path = write_sources_yaml(tmp_path, "sources: []\n")

    notifiers = load_notifiers(path)

    assert notifiers.discord.enabled is False
    assert notifiers.telegram.enabled is False


def test_load_filter_parses_enabled_flag(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        filter:
          enabled: true
        """,
    )

    filter_config = load_filter(path)

    assert filter_config.enabled is True


def test_load_filter_defaults_to_disabled_when_section_missing(
    tmp_path: Path,
) -> None:
    path = write_sources_yaml(tmp_path, "sources: []\n")

    filter_config = load_filter(path)

    assert filter_config.enabled is False


def test_load_filter_parses_model_when_provided(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        filter:
          enabled: true
          model: gemini-3.8-flash
        """,
    )

    filter_config = load_filter(path)

    assert filter_config.model == "gemini-3.8-flash"


def test_load_filter_defaults_model_to_none_when_omitted(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        filter:
          enabled: true
        """,
    )

    filter_config = load_filter(path)

    assert filter_config.model is None


def test_load_cronjob_defaults_when_section_missing(tmp_path: Path) -> None:
    path = write_sources_yaml(tmp_path, "sources: []\n")

    cronjob = load_cronjob(path)

    assert cronjob.enabled is True
    assert cronjob.time == "07:00"
    assert cronjob.timezone == "Asia/Ho_Chi_Minh"


def test_load_cronjob_parses_overrides_when_provided(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          enabled: false
          time: "18:30"
          timezone: America/New_York
        """,
    )

    cronjob = load_cronjob(path)

    assert cronjob.enabled is False
    assert cronjob.time == "18:30"
    assert cronjob.timezone == "America/New_York"


def test_load_cronjob_raises_when_time_format_is_invalid(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          time: "not-a-time"
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.time"):
        load_cronjob(path)


def test_load_cronjob_raises_when_time_includes_seconds(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          time: "07:00:30"
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.time"):
        load_cronjob(path)


def test_load_cronjob_raises_when_time_is_missing_colon(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          time: "0700"
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.time"):
        load_cronjob(path)


def test_load_cronjob_raises_when_time_has_leading_t(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          time: "T07:00"
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.time"):
        load_cronjob(path)


def test_load_cronjob_raises_when_hour_is_out_of_range(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          time: "24:00"
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.time"):
        load_cronjob(path)


def test_load_cronjob_raises_when_timezone_is_invalid(tmp_path: Path) -> None:
    path = write_sources_yaml(
        tmp_path,
        """
        sources: []
        cronjob:
          timezone: Not/AZone
        """,
    )

    with pytest.raises(ValidationError, match="cronjob.timezone"):
        load_cronjob(path)
