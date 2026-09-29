from smartnews.models import Article


def print_article(article: Article) -> None:
    line = f"[{article.source}] {article.title} - {article.url} - {article.published_at}"
    print(line)
