# smartnews

## Goal

`smartnews` is a long-running service that collects RSS feeds from a
configurable list of sources, aggregates and deduplicates the articles,
filters/summarizes them, and forwards the relevant ones to a chat channel
(Discord and/or Telegram).

Pipeline, end to end:

```
Fetcher -> [RabbitMQ] -> Transformation (LLM) -> [RabbitMQ] -> Notification (Discord/Telegram)
```

Each stage runs as its own service; the fetcher runs once daily at a configured
time (`run_at`/`timezone`).

## Architecture

Three services in one uv workspace, talking over RabbitMQ and sharing one
Postgres database:

```
fetcher ──► [articles.fetched] ──► transformation ──► [articles.transformed] ──► notification
```

- **fetcher-service** (`services/fetcher`) — long-running loop that runs
  once a day at a fixed local time.
  Each cycle streams articles through generators: fetch enabled sources →
  drop articles older than `lookback_days` → for each article, unless its
  source already hit `max_posts` new articles this cycle, insert it into
  `articles` (`ON CONFLICT (hash_url) DO NOTHING`) and publish
  `ArticleFetched` inside one transaction, committing only after the
  broker confirms. A failed publish rolls back, so the article is retried
  next cycle.
- **transformation-service** (`services/transformation`) — consumes
  `articles.fetched`, runs the configured `Filter` (Gemini/Groq/passthrough),
  upserts `article_transformations`, publishes `ArticleTransformed`.
  Filters raise `TransformationError`; on the final attempt the article is
  forwarded untranslated (`language=None`) instead of dropped.
- **notification-service** (`services/notification`) — consumes
  `articles.transformed`; for each enabled notifier, skips channels already
  recorded in `article_deliveries`, sends, then records the delivery. If
  any channel fails the message is retried; redeliveries never double-post.
- **smartnews_common** (`libs/common`) — `Article`/`Transformation` model,
  `article_key()` dedup hash, Pydantic message contracts, pika topology /
  publisher / consumer, SQLAlchemy engine, sqlc-generated queries and thin
  stores.

Failures in a consumer go through `<queue>.retry.1m` → `5m` → `15m`
(TTL queues that dead-letter back to the main queue), then `<queue>.dlq`.
The attempt number travels in the `x-attempt` header.

## Database

- Migrations are hand-written SQL in `db/migrations/NNNN_name.{up,down}.sql`
  — the single source of truth. Alembic (`db/alembic/versions/`) executes
  them; sqlc reads the `.up.sql` files as its schema.
- Queries live in `db/queries/*.sql`; run `sqlc generate` after changing
  them or a migration. Never edit `smartnews_common/db/generated/`.
- The legacy `seen_articles` table is unused and can be dropped by hand.

## Config

One file per service under `config/`: `fetcher.yaml`
(`run_at`/`timezone`, `sources[]` with `name`, `url`, `category`,
`enabled`, `max_posts`, `lookback_days`), `transformation.yaml`
(`filter.enabled`, `filter.provider`, `filter.model`),
`notification.yaml` (`notifiers.<channel>.enabled`). Credentials come only
from env: `DATABASE_URL`, `RABBITMQ_URL` for all services;
`GEMINI_API_KEY`/`GROQ_API_KEY` for transformation;
`DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` for
notification. See `services/*/.env.example`.

## Commands

- `uv run pytest` — all tests (needs Docker for testcontainers).
- `sqlc generate` / `sqlc diff` — regenerate / check generated queries.
- `docker compose up -d` — Postgres, RabbitMQ, migrations, all services.
