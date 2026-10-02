# smartnews

## Goal

`smartnews` is a long-running service that collects RSS feeds from a
configurable list of sources, aggregates and deduplicates the articles,
filters/summarizes them, and forwards the relevant ones to a chat channel
(Discord and/or Telegram).

Pipeline, end to end:

```
                                  -> Transformation (LLM) -> [RabbitMQ] -> Notification (Discord/Telegram)
Fetcher -> [RabbitMQ, fanned out]
                                  -> Crawler (full content) -> [RabbitMQ] (no consumer yet)
```

Each stage runs as its own service; the fetcher runs once daily at a configured
time (`run_at`/`timezone`). The crawler runs independently of the transformer and
notifier: `fetcher` publishes once, and RabbitMQ fans that single message out
to both `articles.fetched` and `articles.crawl` (two queues bound to the same
routing key), so a source the crawler cannot fetch never affects delivery.

## Architecture

Four services in one uv workspace, talking over RabbitMQ and sharing one
Postgres database:

```
                       ┌──► [articles.fetched] ──► transformer ──► [articles.transformed] ──► notifier
fetcher ──► (fan-out) ─┤
                       └──► [articles.crawl] ──► crawler ──► [articles.crawled] (no consumer yet)
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
- **transformer-service** (`services/transformer`) — consumes
  `articles.fetched`, runs the `summary` step's configured `Filter`
  (Gemini/Groq/passthrough), upserts `article_transformations`, publishes
  `ArticleTransformed`. A second consumer translates crawled content with
  the `content` step's `ContentTranslator` (Gemini or Groq); each step picks
  its provider and model independently.
  Filters raise `TransformationError`; on the final attempt the article is
  forwarded untranslated (`language=None`) instead of dropped.
- **notifier-service** (`services/notifier`) — consumes
  `articles.transformed`; for each enabled notifier, skips channels already
  recorded in `article_deliveries`, sends, then records the delivery. If
  any channel fails the message is retried; redeliveries never double-post.
- **crawler-service** (`services/crawler`) — consumes `articles.crawl`
  (fanned out from the same `ArticleFetched` message `fetcher` publishes to
  `articles.fetched`), fetches the article's URL over HTTP, extracts its main
  text with `trafilatura` (or a per-source CSS-selector override from
  `config/crawler.yaml`), upserts `article_contents`, and publishes
  `ArticleCrawled` to `articles.crawled`. A failed crawl goes through the
  standard retry ladder and DLQ like every other consumer; nothing downstream
  depends on it, so it never blocks or delays transformer/notifier.
  `articles.crawled` has no consumer yet, so it grows unbounded until one
  exists or an operator sets a RabbitMQ retention policy (`x-max-length` /
  `x-message-ttl`) on it externally.
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
`enabled`, `max_posts`, `lookback_days`), `transformer.yaml`
(`summary` and `content`, each with `enabled`, `provider`, `model`),
`notifier.yaml` (`notifiers.<channel>.enabled`), `crawler.yaml`
(`timeout_seconds`, `user_agent`, `overrides.<source-slug>.content_selector`).
Credentials come only from env: `DATABASE_URL`, `RABBITMQ_URL` for all
services; `GEMINI_API_KEY`/`GROQ_API_KEY` for transformer;
`DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` for
notifier. The crawler needs no API key. See `services/*/.env.example`.

## Commands

- `uv run pytest` — all tests (needs Docker for testcontainers).
- `sqlc generate` / `sqlc diff` — regenerate / check generated queries.
- `docker compose up -d` — Postgres, RabbitMQ, migrations, all services.
