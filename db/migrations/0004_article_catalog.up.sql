-- Read model for the articles API: both languages side by side. The API
-- decides which language's columns to require and return.
CREATE VIEW article_catalog AS
SELECT a.id,
       a.title        AS title_en,
       t.title        AS title_vi,
       a.summary      AS summary_en,
       t.summary      AS summary_vi,
       c.content      AS content_en,
       t.content      AS content_vi,
       a.thumbnail,
       a.published_at,
       a.url,
       a.source,
       a.category,
       -- published_at is optional in feeds; created_at keeps the ordering total.
       COALESCE(a.published_at, a.created_at) AS sort_at
FROM articles a
LEFT JOIN article_transformations t ON t.article_id = a.id
LEFT JOIN article_contents        c ON c.article_id = a.id;
