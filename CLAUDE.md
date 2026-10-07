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
A separate read-only `api` service serves the stored articles to a frontend
news reader over HTTP.

## Architecture

Six services in one uv workspace. All six share one Postgres database (the
redriver only reads it); the four pipeline services and the redriver talk
over RabbitMQ:

```
                       ┌──► [articles.fetched] ──► transformer ──► [articles.transformed] ──► notifier
fetcher ──► (fan-out) ─┤
                       └──► [articles.crawl] ──► crawler ──► [articles.crawled] (no consumer yet)

[articles.crawl.dlq] ──(hourly)──► redriver ──(default exchange)──► [articles.crawl]
articles (untranslated) ──(hourly)──► redriver ──(default exchange)──► [articles.fetched]
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
  (Gemini/Groq/OpenCode Go/passthrough), upserts `article_transformations`, publishes
  `ArticleTransformed`. A second consumer translates crawled content with
  the `content` step's `ContentTranslator` (Gemini, Groq or OpenCode Go); each step picks
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
- **api-service** (`services/api`) — read-only Flask app (gunicorn, port
  8000) for the frontend news reader. `GET /articles?lang=en|vi` returns a
  cursor-paginated list (`limit`, `cursor`, optional `category`/`source`)
  and `GET /articles/<id>?lang=en|vi` returns one article with its content.
  It reads the `article_catalog` view, which holds both languages side by
  side; `language.py` picks the requested one. An article appears only when
  its title, summary, content and thumbnail exist in that language (the
  list checks content too but does not return it). No RabbitMQ.
- **redriver-service** (`services/redriver`) — long-running loop that, at
  the top of every hour in its `timezone`, moves each configured
  `<queue>.dlq` back to `<queue>` through the default exchange (so a
  redriven crawl reaches only the crawler, never the transformer), with
  `x-attempt` reset to 1 so it gets the full retry ladder again. Each pass
  redrives at most the DLQ depth seen when it started, capped at
  `max_messages_per_run` per DLQ (the rest wait for the next hour), one
  message at a time with `delay_seconds` between messages, and acks a DLQ message only
  after the broker confirmed its republish. Redrives are unlimited: a
  permanently broken URL cycles DLQ → crawl → retries → DLQ every hour.
  Only `articles.crawl` is configured. It never declares queues; a missing
  DLQ is logged and skipped.
  A second, independent job, **retransform** (own thread, same hourly
  schedule, on unless `retransform.enabled: false`), selects up to
  `max_messages_per_run` articles at least `retransform.min_age_minutes` old
  whose title and summary were never translated (no
  `article_transformations` row, or one holding only content), oldest
  first, and republishes each as `ArticleFetched` to `articles.fetched`
  through the default exchange (so it is not re-crawled), `delay_seconds`
  apart. It only reads the database. An article that never translates is
  republished every hour; channels that already received it are skipped by
  the notifier.
- **smartnews_common** (`libs/common`) — `Article`/`Transformation` model,
  `article_key()` dedup hash, Pydantic message contracts, pika topology /
  publisher / consumer, SQLAlchemy engine, sqlc-generated queries and thin
  stores.

Failures in a consumer go through `<queue>.retry.1m` → `5m` → `15m`
(TTL queues that dead-letter back to the main queue), then `<queue>.dlq`.
The attempt number travels in the `x-attempt` header. The redriver drains
the configured DLQs (today only `articles.crawl.dlq`) back into their main
queue every hour.

## Database

- Migrations are hand-written SQL in `db/migrations/NNNN_name.{up,down}.sql`
  — the single source of truth. Alembic (`db/alembic/versions/`) executes
  them; sqlc reads the `.up.sql` files as its schema.
- Queries live in `db/queries/*.sql`; run `sqlc generate` after changing
  them or a migration. Never edit `smartnews_common/db/generated/`.
- The legacy `seen_articles` table is unused and can be dropped by hand.
- `article_catalog` (migration 0004) is a read-only view joining `articles`,
  `article_transformations` and `article_contents` into `_en`/`_vi` columns
  plus `sort_at = COALESCE(published_at, created_at)`.

## Config

One file per service under `config/`: `fetcher.yaml`
(`run_at`/`timezone`, `sources[]` with `name`, `url`, `category`,
`enabled`, `max_posts`, `lookback_days`), `transformer.yaml`
(`run_once` — handle one message per queue and exit; `summary` and `content`,
each with `enabled`, `provider`, `model`,
`delay_seconds` — minimum spacing between that step's LLM calls),
`notifier.yaml` (`notifiers.<channel>.enabled`), `crawler.yaml`
(`timeout_seconds`, `user_agent`, `overrides.<source-slug>.content_selector`),
`api.yaml` (`cors_allowed_origins`, `default_page_size`, `max_page_size`),
`redriver.yaml` (`timezone`, `run_once`, `delay_seconds`,
`max_messages_per_run`, `queues`, `retransform.enabled`,
`retransform.min_age_minutes`).
Credentials come only from env: `DATABASE_URL` for all services (the
redriver only while `retransform.enabled` is true), `RABBITMQ_URL` for all but api; `GEMINI_API_KEY`/`GROQ_API_KEY`/`OPENCODE_GO_API_KEY` for transformer;
`DISCORD_WEBHOOK_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` for
notifier. The crawler, api and redriver need no API key; the redriver
needs only `RABBITMQ_URL`, plus `DATABASE_URL` for retransform. See
`services/*/.env.example`.

## Commands

- `uv run pytest` — all tests (needs Docker for testcontainers).
- `sqlc generate` / `sqlc diff` — regenerate / check generated queries.
- `docker compose up -d` — Postgres, RabbitMQ, migrations, all services.
