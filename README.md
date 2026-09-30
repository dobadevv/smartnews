# smartnews

## Introduction

### Goal

`smartnews` watches a configurable list of RSS/Atom feeds — engineering
blogs, release notes, AI news, markets, world news, and more — and pushes
only the new, relevant articles to a Discord and/or Telegram channel, with
an optional LLM pass that translates and summarizes each article before it
is sent.

### The problem

Keeping up with dozens of feeds by hand doesn't scale:

- Checking every source manually is slow and easy to fall behind on.
- Plain RSS readers show everything, including articles you've already
  seen across multiple runs or devices.
- Titles and summaries are often verbose, in English only, and not
  tailored to what you actually want to skim.

### The solution

`smartnews` automates the whole loop:

1. **Fetch** every enabled source's feed.
2. **Deduplicate** against a Postgres-backed store, so the same article is
   never sent twice on the same channel, even across separate runs.
3. **Filter/translate** each surviving article with an LLM (Gemini or
   Groq), rewriting the title/summary into a short, Vietnamese-language
   overview while keeping technical terms untouched.
4. **Notify** the configured channel(s) — Discord and/or Telegram — with
   the final result.

Each stage is isolated: a fetch failure on one source, a translation
failure on one article, or a send failure on one notifier only affects
that item, never the rest of the run.

## How it works

```
fetcher ──► [articles.fetched] ──► transformation ──► [articles.transformed] ──► notification
```

1. **fetcher** fetches every enabled feed once a day at a fixed local time,
   drops stale articles, stores new ones in Postgres and publishes them.
2. **transformation** translates each article's title and summary to
   Vietnamese with Gemini or Groq and stores the result.
3. **notification** posts each article to Discord and/or Telegram and
   records which channels received it, so nothing is posted twice.

Failed steps are retried after 1, 5 and 15 minutes, then parked in a
dead-letter queue visible in the RabbitMQ UI (http://localhost:15672).

## Usage

### Requirements

- Docker with Compose
- For development: [uv](https://docs.astral.sh/uv/) and [sqlc](https://sqlc.dev/)

### Configuration

- `config/fetcher.yaml` — `run_at`/`timezone` and the source list.
- `config/transformation.yaml` — LLM filter on/off, provider, model.
- `config/notification.yaml` — which channels are enabled.
- Secrets: copy `services/transformation/.env.example` and
  `services/notification/.env.example` to `.env` next to them and fill in
  the keys for what you enabled.

### Running

```bash
docker compose up -d --build
docker compose logs -f fetcher transformation notification
```

Migrations run automatically before the services start.

### Development

```bash
uv run pytest       # run the test suite
uv run ruff check    # lint
```
