CREATE TABLE articles (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hash_url      TEXT        NOT NULL UNIQUE,
    url           TEXT        NOT NULL,
    title         TEXT        NOT NULL,
    summary       TEXT,
    published_at  TIMESTAMPTZ,
    source        TEXT        NOT NULL,
    thumbnail     TEXT,
    category      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE article_transformations (
    article_id  BIGINT      PRIMARY KEY REFERENCES articles (id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    summary     TEXT,
    language    TEXT        NOT NULL CHECK (language IN ('vi')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE article_deliveries (
    article_id    BIGINT      NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    channel       TEXT        NOT NULL,
    delivered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, channel)
);
