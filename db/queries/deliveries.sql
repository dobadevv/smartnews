-- name: IsDelivered :one
SELECT EXISTS (
    SELECT 1 FROM article_deliveries
    WHERE article_id = sqlc.arg(article_id) AND channel = sqlc.arg(channel)
) AS delivered;

-- name: MarkDelivered :exec
INSERT INTO article_deliveries (article_id, channel)
VALUES (sqlc.arg(article_id), sqlc.arg(channel))
ON CONFLICT (article_id, channel) DO NOTHING;
