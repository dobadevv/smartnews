from smartnews_common.models import Article
from smartnews_transformation.filtering.passthrough import PassthroughFilter


def test_transform_leaves_articles_untranslated() -> None:
    article = Article(
        title="Hello", url="https://example.com/a", source="s", published_at=None, summary="S"
    )

    assert PassthroughFilter().transform(article) is None
