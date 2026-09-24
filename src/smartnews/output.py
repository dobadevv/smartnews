from smartnews.models import Article


def print_articles(articles: list[Article]) -> None:
    for article in articles:
        print(f"[{article.source}] {article.title} - {article.url}")
