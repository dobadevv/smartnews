from smartnews.dedup import article_key
from smartnews.models import Article


def make_article(url: str) -> Article:
    return Article(
        title="Some Title",
        url=url,
        source="example-blog",
        published_at=None,
        summary=None,
    )


def test_article_key_is_stable_for_the_same_url() -> None:
    article = make_article("https://example.com/hello-world")

    assert article_key(article) == article_key(article)


def test_article_key_differs_for_different_urls() -> None:
    a = make_article("https://example.com/hello-world")
    b = make_article("https://example.com/goodbye-world")

    assert article_key(a) != article_key(b)


def test_article_key_ignores_tracking_query_params() -> None:
    a = make_article("https://example.com/hello-world")
    b = make_article(
        "https://example.com/hello-world?utm_source=newsletter&utm_medium=email"
    )

    assert article_key(a) == article_key(b)


def test_article_key_ignores_url_fragment() -> None:
    a = make_article("https://example.com/hello-world")
    b = make_article("https://example.com/hello-world#section-2")

    assert article_key(a) == article_key(b)
