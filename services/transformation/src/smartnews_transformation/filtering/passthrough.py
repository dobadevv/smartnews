from smartnews_common.models import Article, Transformation


class PassthroughFilter:
    def transform(self, article: Article) -> Transformation | None:
        return None
