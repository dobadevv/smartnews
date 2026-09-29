from smartnews.models import Article


class PassthroughFilter:
    def filter(self, article: Article) -> Article:
        return article
