from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict

from smartnews_common.dedup import article_key
from smartnews_common.models import Article, Language, Transformation


class ArticleMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    article_id: int
    hash_url: str
    url: str
    title: str
    summary: str | None
    published_at: datetime | None
    source: str
    thumbnail: str | None
    category: str | None

    def to_article(self) -> Article:
        return Article(
            title=self.title,
            url=self.url,
            source=self.source,
            published_at=self.published_at,
            summary=self.summary,
            thumbnail=self.thumbnail,
            category=self.category,
        )


class ArticleFetched(ArticleMessage):
    @classmethod
    def from_article(cls, article: Article, article_id: int) -> Self:
        return cls(
            article_id=article_id,
            hash_url=article_key(article),
            url=article.url,
            title=article.title,
            summary=article.summary,
            published_at=article.published_at,
            source=article.source,
            thumbnail=article.thumbnail,
            category=article.category,
        )


class ArticleTransformed(ArticleMessage):
    language: Language | None

    @classmethod
    def translated(cls, fetched: ArticleFetched, transformation: Transformation) -> Self:
        return cls(
            **fetched.model_dump()
            | {"title": transformation.title, "summary": transformation.summary},
            language=transformation.language,
        )

    @classmethod
    def untranslated(cls, fetched: ArticleFetched) -> Self:
        return cls(**fetched.model_dump(), language=None)


class ArticleCrawled(ArticleMessage):
    content: str

    @classmethod
    def from_fetched(cls, fetched: ArticleFetched, content: str) -> Self:
        return cls(**fetched.model_dump(), content=content)
