import pytest

from smartnews.models import Article
from smartnews.output import print_articles


def test_print_articles_prints_one_line_per_article(
    capsys: pytest.CaptureFixture[str],
) -> None:
    articles = [
        Article(
            title="Hello World",
            url="https://example.com/hello-world",
            source="example-blog",
            published_at=None,
            summary=None,
        ),
        Article(
            title="Second Post",
            url="https://example.com/second-post",
            source="another-source",
            published_at=None,
            summary=None,
        ),
    ]

    print_articles(articles)

    out = capsys.readouterr().out
    assert out == (
        "[example-blog] Hello World - https://example.com/hello-world\n"
        "[another-source] Second Post - https://example.com/second-post\n"
    )
