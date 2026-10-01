-- Fails if any row was created by the content writer alone (title IS NULL).
ALTER TABLE article_transformations DROP COLUMN content;
ALTER TABLE article_transformations ALTER COLUMN title SET NOT NULL;
