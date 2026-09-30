-- name: InsertArticleIfAbsent :one
INSERT INTO articles (hash_url, url, title, summary, published_at, source, thumbnail, category)
VALUES (
    sqlc.arg(hash_url), sqlc.arg(url), sqlc.arg(title), sqlc.narg(summary),
    sqlc.narg(published_at), sqlc.arg(source), sqlc.narg(thumbnail), sqlc.narg(category)
)
ON CONFLICT (hash_url) DO NOTHING
RETURNING id;
