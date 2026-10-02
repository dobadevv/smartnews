from collections.abc import Callable

import pytest
from smartnews_api.wsgi import build_app


def test_api_lists_then_shows_an_article_from_the_database(
    monkeypatch: pytest.MonkeyPatch,
    migrated_database_url: str,
    insert_catalog_article: Callable[..., int],
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    article_id = insert_catalog_article(
        title_vi="Tiêu đề", summary_vi="Tóm tắt", content_vi="Nội dung"
    )
    client = build_app().test_client()

    listing = client.get("/articles?lang=vi&limit=10")
    [item] = listing.get_json()["items"]
    detail = client.get(f"/articles/{item['id']}?lang=vi")

    assert listing.status_code == 200
    assert (item["id"], item["title"], item["summary"]) == (article_id, "Tiêu đề", "Tóm tắt")
    assert detail.status_code == 200
    assert detail.get_json()["content"] == "Nội dung"
