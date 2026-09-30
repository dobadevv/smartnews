-- name: UpsertArticleContent :exec
INSERT INTO article_contents (article_id, content, extractor)
VALUES (sqlc.arg(article_id), sqlc.arg(content), sqlc.arg(extractor))
ON CONFLICT (article_id) DO UPDATE
SET content = EXCLUDED.content,
    extractor = EXCLUDED.extractor,
    crawled_at = now();
