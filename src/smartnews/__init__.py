from pathlib import Path

from smartnews.config import load_sources
from smartnews.fetching.rss import RssFetcher
from smartnews.output import print_articles
from smartnews.pipeline import fetch_enabled_sources

DEFAULT_CONFIG_PATH = Path("config/sources.yaml")


def main() -> None:
    sources = load_sources(DEFAULT_CONFIG_PATH)
    articles = fetch_enabled_sources(sources, RssFetcher())
    print_articles(articles)
