import pytest
from smartnews_fetcher.text import html_to_text


@pytest.mark.parametrize(
    ("html", "want"),
    [
        pytest.param(None, None, id="none_stays_none"),
        pytest.param("Plain text", "Plain text", id="plain_text_is_unchanged"),
        pytest.param(
            "<p>Article URL: <a href='https://example.com'>https://example.com</a></p>",
            "Article URL: https://example.com",
            id="strips_tags_and_keeps_link_text",
        ),
        pytest.param(
            "<p>Points: 22</p><p># Comments: 13</p>",
            "Points: 22 # Comments: 13",
            id="joins_separate_paragraphs_with_a_space",
        ),
        pytest.param(
            "Fish &amp; Chips",
            "Fish & Chips",
            id="decodes_html_entities",
        ),
    ],
)
def test_html_to_text(html: str | None, want: str | None) -> None:
    assert html_to_text(html) == want
