from smartnews_common.models import Article
from smartnews_transformation.filtering.prompts import (
    build_content_translation_prompt,
    build_translation_prompt,
)


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


def test_build_content_translation_prompt_asks_for_a_concise_vietnamese_rewrite() -> None:
    prompt = build_content_translation_prompt("Original content.").lower()

    assert "vietnamese" in prompt
    assert "concise" in prompt
    assert "do not summarize" not in prompt


def test_build_content_translation_prompt_asks_for_an_introduction_body_and_conclusion() -> None:
    prompt = build_content_translation_prompt("Original content.").lower()

    assert all(part in prompt for part in ("introduction", "body", "conclusion"))


def test_build_content_translation_prompt_asks_for_plain_text_without_special_characters() -> None:
    prompt = build_content_translation_prompt("Original content.").lower()

    assert "plain text" in prompt
    assert "markdown" in prompt


def test_build_content_translation_prompt_keeps_technical_terms_in_english() -> None:
    prompt = build_content_translation_prompt("Original content.")

    assert "technical" in prompt
    assert "original English form" in prompt


def test_build_content_translation_prompt_ends_with_the_content() -> None:
    prompt = build_content_translation_prompt("Original content.")

    assert prompt.endswith("Original content.")
