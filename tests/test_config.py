from pathlib import Path

from smartnews.config import load_sources


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
