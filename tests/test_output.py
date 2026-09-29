import pytest

from smartnews.models import Article
from smartnews.output import print_article


def test_print_article_prints_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    print_article(article)

    out = capsys.readouterr().out
    assert out == "[example-blog] Hello World - https://example.com/hello-world\n"


def test_print_article_includes_thumbnail_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
        thumbnail="https://example.com/hello-world.jpg",
    )

    print_article(article)

    out = capsys.readouterr().out
    assert out == (
        "[example-blog] Hello World - https://example.com/hello-world "
        "- https://example.com/hello-world.jpg\n"
    )
