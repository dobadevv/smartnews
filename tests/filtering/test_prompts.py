from smartnews.filtering.prompts import build_translation_prompt
from smartnews.models import Article


def make_article(
    title: str = "Hello World", summary: str | None = "Original summary."
) -> Article:
    return Article(
        title=title,
        url="https://example.com/hello-world",
        source="example-blog",
        published_at=None,
        summary=summary,
    )


def test_build_translation_prompt_mentions_json() -> None:
    prompt = build_translation_prompt(make_article())

    assert "json" in prompt.lower()
