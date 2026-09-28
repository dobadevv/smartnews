from smartnews.models import Article


def print_articles(articles: list[Article]) -> None:
    for article in articles:
        line = f"[{article.source}] {article.title} - {article.url}"
        if article.thumbnail:
            line += f" - {article.thumbnail}"
        print(line)
