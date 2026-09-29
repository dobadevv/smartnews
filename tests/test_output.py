from datetime import UTC, datetime

import pytest

from smartnews.models import Article
from smartnews.output import print_article


def test_print_article_prints_one_line_with_published_at(
    capsys: pytest.CaptureFixture[str],
) -> None:
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=datetime(2024, 1, 1, tzinfo=UTC),
        summary=None,
    )

    print_article(article)

    out = capsys.readouterr().out
    assert out == (
        "[example-blog] Hello World - https://example.com/hello-world "
        "- 2024-01-01 00:00:00+00:00\n"
    )


def test_print_article_prints_none_when_published_at_is_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    article = Article(
        title="Hello World",
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=None,
    )

    print_article(article)

    out = capsys.readouterr().out
    assert out == "[example-blog] Hello World - https://example.com/hello-world - None\n"
