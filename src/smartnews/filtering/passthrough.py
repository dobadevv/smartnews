from smartnews.models import Article


class PassthroughFilter:
    def filter(self, articles: list[Article]) -> list[Article]:
        return articles
