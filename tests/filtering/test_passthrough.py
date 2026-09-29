from smartnews.filtering.passthrough import PassthroughFilter
from smartnews.models import Article


def test_filter_returns_articles_unchanged() -> None:
    articles = [
        Article(
            title="Hello World",
            url="https://example.com/hello-world",
            source="example-blog",
            published_at=None,
            summary="A summary.",
        )
    ]

    result = PassthroughFilter().filter(articles)

    assert result == articles
