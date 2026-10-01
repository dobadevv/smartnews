-- name: UpsertArticleTransformation :exec
INSERT INTO article_transformations (article_id, title, summary, language)
VALUES (sqlc.arg(article_id), sqlc.arg(title), sqlc.narg(summary), sqlc.arg(language))
ON CONFLICT (article_id) DO UPDATE
SET title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    language = EXCLUDED.language;


-- name: UpsertArticleTransformationContent :exec
INSERT INTO article_transformations (article_id, language, content)
VALUES (sqlc.arg(article_id), 'vi', sqlc.arg(content))
ON CONFLICT (article_id) DO UPDATE
SET content = EXCLUDED.content;
