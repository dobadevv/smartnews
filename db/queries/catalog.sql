-- name: ListCatalogArticles :many
-- Content is required but not selected: the list never returns it, and every
-- listed article must open in the detail endpoint.
SELECT id, title_en, title_vi, summary_en, summary_vi,
       thumbnail, published_at, url, source, category, sort_at
FROM article_catalog
WHERE (
        (sqlc.arg(language)::text = 'en'
         AND title_en IS NOT NULL AND summary_en IS NOT NULL AND content_en IS NOT NULL)
     OR (sqlc.arg(language)::text = 'vi'
         AND title_vi IS NOT NULL AND summary_vi IS NOT NULL AND content_vi IS NOT NULL)
      )
  AND thumbnail IS NOT NULL
  AND (sqlc.narg(category)::text IS NULL OR category = sqlc.narg(category)::text)
  AND (sqlc.narg(source)::text IS NULL OR source = sqlc.narg(source)::text)
  AND (sqlc.narg(sort_at_from)::timestamptz IS NULL OR sort_at >= sqlc.narg(sort_at_from)::timestamptz)
  AND (sqlc.narg(sort_at_to)::timestamptz   IS NULL OR sort_at <  sqlc.narg(sort_at_to)::timestamptz)
  AND (
        sqlc.narg(cursor_sort_at)::timestamptz IS NULL
     OR (sort_at, id) < (sqlc.narg(cursor_sort_at)::timestamptz, sqlc.narg(cursor_id)::bigint)
      )
ORDER BY sort_at DESC, id DESC
LIMIT sqlc.arg(page_size)::int;

-- name: GetCatalogArticle :one
SELECT *
FROM article_catalog
WHERE id = sqlc.arg(article_id)::bigint
  AND thumbnail IS NOT NULL
  AND (
        (sqlc.arg(language)::text = 'en'
         AND title_en IS NOT NULL AND summary_en IS NOT NULL AND content_en IS NOT NULL)
     OR (sqlc.arg(language)::text = 'vi'
         AND title_vi IS NOT NULL AND summary_vi IS NOT NULL AND content_vi IS NOT NULL)
      );

-- name: CountCatalogArticlesByCategory :many
-- Eligibility is copied from ListCatalogArticles (sqlc has no fragments): each
-- count is the number of articles /articles would list for that category.
SELECT category, COUNT(*)::bigint AS article_count
FROM article_catalog
WHERE (
        (sqlc.arg(language)::text = 'en'
         AND title_en IS NOT NULL AND summary_en IS NOT NULL AND content_en IS NOT NULL)
     OR (sqlc.arg(language)::text = 'vi'
         AND title_vi IS NOT NULL AND summary_vi IS NOT NULL AND content_vi IS NOT NULL)
      )
  AND thumbnail IS NOT NULL
  AND category IS NOT NULL
  AND (sqlc.narg(sort_at_from)::timestamptz IS NULL OR sort_at >= sqlc.narg(sort_at_from)::timestamptz)
  AND (sqlc.narg(sort_at_to)::timestamptz   IS NULL OR sort_at <  sqlc.narg(sort_at_to)::timestamptz)
GROUP BY category;

-- name: CountCatalogArticlesBySource :many
-- Eligibility is copied from ListCatalogArticles (sqlc has no fragments): each
-- count is the number of articles /articles would list for that source.
SELECT source, COUNT(*)::bigint AS article_count
FROM article_catalog
WHERE (
        (sqlc.arg(language)::text = 'en'
         AND title_en IS NOT NULL AND summary_en IS NOT NULL AND content_en IS NOT NULL)
     OR (sqlc.arg(language)::text = 'vi'
         AND title_vi IS NOT NULL AND summary_vi IS NOT NULL AND content_vi IS NOT NULL)
      )
  AND thumbnail IS NOT NULL
  AND (sqlc.narg(sort_at_from)::timestamptz IS NULL OR sort_at >= sqlc.narg(sort_at_from)::timestamptz)
  AND (sqlc.narg(sort_at_to)::timestamptz   IS NULL OR sort_at <  sqlc.narg(sort_at_to)::timestamptz)
GROUP BY source;
