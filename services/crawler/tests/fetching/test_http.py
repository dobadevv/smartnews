import pytest
from pytest_httpserver import HTTPServer
from smartnews_crawler.fetching.base import FetchError
from smartnews_crawler.fetching.http import HttpPageFetcher
from werkzeug.wrappers import Response


def test_fetch_returns_the_response_body(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/article").respond_with_data(
        "<html><body>Hello</body></html>", content_type="text/html"
    )

    html = HttpPageFetcher().fetch(httpserver.url_for("/article"))

    assert b"Hello" in html


def test_fetch_returns_raw_bytes_preserving_a_charset_the_headers_do_not_declare(
    httpserver: HTTPServer,
) -> None:
    """requests defaults text/* with no charset parameter to ISO-8859-1, which
    would corrupt non-ASCII text decoded at this layer. The fetcher must hand
    back untouched bytes so extraction can sniff the page's own <meta
    charset> declaration instead.
    """
    original_text = "Tiếng Việt"
    body = f"<html><head><meta charset=\"utf-8\"></head><body>{original_text}</body></html>"
    httpserver.expect_request("/article").respond_with_data(
        body.encode("utf-8"), content_type="text/html"
    )

    html = HttpPageFetcher().fetch(httpserver.url_for("/article"))

    assert original_text.encode("utf-8") in html
    assert original_text in html.decode("utf-8")


def test_fetch_sends_a_browser_like_user_agent(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/article").respond_with_data("ok")

    HttpPageFetcher(user_agent="TestBot/1.0").fetch(httpserver.url_for("/article"))

    assert httpserver.log[0][0].headers.get("User-Agent") == "TestBot/1.0"


def test_fetch_raises_fetch_error_on_a_bot_block_response(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/article").respond_with_response(Response(status=403))

    with pytest.raises(FetchError, match="/article"):
        HttpPageFetcher().fetch(httpserver.url_for("/article"))


def test_fetch_raises_fetch_error_when_the_server_is_unreachable() -> None:
    with pytest.raises(FetchError):
        HttpPageFetcher(timeout_seconds=1.0).fetch("http://localhost:1/unreachable")
