from pathlib import Path

from smartnews_crawler.config import ContentSelectorOverride, CrawlerConfig, load_crawler_config


def test_load_crawler_config_parses_overrides(tmp_path: Path) -> None:
    path = tmp_path / "crawler.yaml"
    path.write_text(
        "timeout_seconds: 20\n"
        "user_agent: TestBot/1.0\n"
        "overrides:\n"
        "  some-source:\n"
        "    content_selector: div.article-body\n"
    )

    config = load_crawler_config(path)

    assert config.timeout_seconds == 20
    assert config.user_agent == "TestBot/1.0"
    assert config.overrides == {
        "some-source": ContentSelectorOverride(content_selector="div.article-body")
    }


def test_load_crawler_config_defaults_to_no_overrides(tmp_path: Path) -> None:
    path = tmp_path / "crawler.yaml"
    path.write_text("")

    config = load_crawler_config(path)

    assert config.timeout_seconds == 15.0
    assert config.overrides == {}
