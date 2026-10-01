-- The translated content is written by a consumer independent of the one that
-- writes title/summary, so either may create the row first.
ALTER TABLE article_transformations ALTER COLUMN title DROP NOT NULL;
ALTER TABLE article_transformations ADD COLUMN content TEXT;
