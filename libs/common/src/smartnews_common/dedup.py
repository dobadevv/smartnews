import hashlib
from urllib.parse import urlsplit, urlunsplit

from smartnews_common.models import Article


def _canonical_url(url: str) -> str:
    scheme, netloc, path, _query, _fragment = urlsplit(url)
    return urlunsplit((scheme, netloc, path, "", ""))


def article_key(article: Article) -> str:
    canonical_url = _canonical_url(article.url)
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
