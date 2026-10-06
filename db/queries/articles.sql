-- name: InsertArticleIfAbsent :one
INSERT INTO articles (hash_url, url, title, summary, published_at, source, thumbnail, category)
VALUES (
    sqlc.arg(hash_url), sqlc.arg(url), sqlc.arg(title), sqlc.narg(summary),
    sqlc.narg(published_at), sqlc.arg(source), sqlc.narg(thumbnail), sqlc.narg(category)
)
ON CONFLICT (hash_url) DO NOTHING
RETURNING id;

-- name: ListUntransformedArticles :many
-- Articles whose title and summary were never translated, oldest first.
-- A transformation row holding only crawled content still counts as untranslated.
SELECT a.id, a.hash_url, a.url, a.title, a.summary, a.published_at,
       a.source, a.thumbnail, a.category
FROM articles a
LEFT JOIN article_transformations t ON t.article_id = a.id
WHERE t.title IS NULL
  AND t.summary IS NULL
  AND a.created_at <= now() - make_interval(mins => sqlc.arg(min_age_minutes)::int)
ORDER BY a.created_at ASC, a.id ASC
LIMIT sqlc.arg(max_rows)::int;
