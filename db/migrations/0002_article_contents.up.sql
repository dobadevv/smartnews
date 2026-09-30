CREATE TABLE article_contents (
    article_id  BIGINT      PRIMARY KEY REFERENCES articles (id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,
    extractor   TEXT        NOT NULL,
    crawled_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
