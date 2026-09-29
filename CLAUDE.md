# smartnews

## Goal

`smartnews` is a long-running service that collects RSS feeds from a
configurable list of sources, aggregates and deduplicates the articles,
filters/summarizes them, and forwards the relevant ones to a chat channel
(Discord and/or Telegram).

Pipeline, end to end:

```
Fetcher(s) -> Aggregator -> Deduper (Postgres) -> Filter (LLM) -> Notifier(s) (Discord/Telegram)
```

The service runs as a self-contained process with an internal scheduler
(no external cron needed): every N minutes it fetches from all enabled
sources, drops articles already seen, runs them through a filter, and
sends whatever survives to the configured channel(s).

## Architecture

Each pipeline stage is defined as an interface (ABC/Protocol) plus one or
more implementations, so stages can be swapped or mocked independently.

- **Fetcher** — reads a source definition and returns a list of
  `Article` domain objects. Current/only implementation wraps
  `feedparser` for RSS/Atom feeds.
- **Repository (dedup store)** — checks whether an article (by a hash of
  its canonicalized URL, computed in `dedup.py`) has already been sent
  **on a given channel**, and records new sends. Backed by Postgres,
  with a `(key, channel)` unique constraint so the same article can be
  independently tracked per Discord/Telegram. An article is only marked
  seen for a channel after it has actually been sent there — if sending
  fails, it stays eligible for a retry on the next cycle instead of
  being silently dropped.
- **Filter** — takes a list of articles and returns the (possibly
  rewritten) list that should be forwarded. Default is `PassthroughFilter`
  (no-op). `GeminiFilter` and `GroqFilter` both call a free-tier LLM API to
  rewrite each article's title/summary: translated to Vietnamese, technical
  terms (product names, languages, frameworks, acronyms like API/LLM/SDK)
  left untranslated, and the summary rewritten as a brief 1-2 sentence
  overview; both share the same prompt via `filtering/prompts.py`. A
  failed call for one article is logged and that article is kept with its
  original title/summary rather than dropped. `filtering/factory.py` builds the
  active `Filter` from config + env (dispatching on `filter.provider`),
  same pattern as notifiers.
- **Notifier** — sends a list of articles to a destination channel.
  Implementations: `DiscordNotifier` (webhook), `TelegramNotifier` (bot
  API). Which notifier(s) are active is controlled by
  `notifiers.<channel>.enabled` in `config/sources.yaml`; credentials
  (webhook URL, bot token, chat id) come from environment variables, not
  the YAML file, so they never get committed. `notifiers/factory.py`
  builds the active `Notifier` list from config + env, raising a clear
  error if a channel is enabled but its env vars are missing.
- **Pipeline** — orchestrates one fetch -> dedup -> filter -> send cycle
  using whichever implementations are wired in. `main()` currently falls
  back to printing articles to stdout when no notifier is enabled, so
  the service still runs without any external setup.
- **Scheduler** — runs the pipeline on a configured interval, keeping the
  process alive as a long-running service.

## File Organization

```
src/smartnews/
  config.py           # load & validate config.yaml (pydantic models)
  models.py            # Article domain model
  dedup.py             # article_key(): canonical-URL hash used as the dedup key
  fetching/
    base.py            # Fetcher interface
    rss.py              # feedparser-based implementation
  repository/
    base.py            # SeenStore interface (dedup store, per channel)
    postgres.py         # Postgres implementation
  filtering/
    base.py            # Filter interface
    passthrough.py      # no-op filter (default)
    prompts.py            # shared translate + brief-summary prompt
    gemini.py            # Gemini-backed filter
    groq.py               # Groq-backed filter (OpenAI-compatible API)
    factory.py           # builds the active filter from config + env vars
  notifiers/
    base.py            # Notifier interface
    discord.py
    telegram.py
    factory.py           # builds active notifiers from config + env vars
  pipeline.py           # one fetch -> dedup -> filter -> send cycle
  scheduler.py           # runs the pipeline on an interval
  __init__.py            # main() entrypoint / service bootstrap
config/
  sources.yaml            # list of RSS sources (name, url, enabled)
```

## Program Flow

1. `main()` loads `config/sources.yaml` (sources, notifier settings,
   filter settings, poll interval).
2. The scheduler starts and, on each tick:
   a. Fetch: for every source with `enabled: true`, fetch its feed and
      parse entries into `Article` objects.
   b. Aggregate: merge articles from all sources into one list.
   c. Filter: run the articles through the configured `Filter`
      implementation.
   d. For each active `Notifier` (its own channel, e.g. `"discord"`,
      `"telegram"`):
      i. Dedup: compute each article's key (`dedup.py`) and ask the
         `SeenStore` which ones are not yet seen on this channel.
      ii. Send: pass the still-unseen articles to this notifier.
      iii. Record: for the articles that were sent successfully, mark
           them seen on this channel in Postgres.
3. The process keeps running, repeating step 2 on the configured
   interval, until stopped.

## Config

`config/sources.yaml` defines which sources are allowed to be fetched:

```yaml
sources:
  - name: example-blog
    url: https://example.com/feed.xml
    enabled: true
  - name: another-source
    url: https://another.example.com/rss
    enabled: false
```

Only sources with `enabled: true` are fetched.

The same file also controls which notifiers are active:

```yaml
notifiers:
  discord:
    enabled: false
  telegram:
    enabled: false
```

Credentials are never stored in this file; they're read from environment
variables at startup, only for the channels that are enabled:

- Discord: `DISCORD_WEBHOOK_URL`
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

Whenever at least one notifier is enabled, `DATABASE_URL` (a Postgres
connection string) is also required, since dedup state is stored there.

The same file also controls whether the LLM filter runs:

```yaml
filter:
  enabled: false
  provider: gemini            # "gemini" (default) or "groq"
  model: gemini-3.8-flash     # optional; defaults to the provider's own default
```

When enabled with `provider: gemini` (the default), `GEMINI_API_KEY` must
be set (free tier key from https://aistudio.google.com/apikey). When
enabled with `provider: groq`, `GROQ_API_KEY` must be set instead (free
tier key from https://console.groq.com/keys) — Groq's free tier has
noticeably higher rate limits, useful if Gemini's free-tier quota
(20 requests/min on `gemini-3.8-flash`) gets exhausted by a single fetch
batch. `model` lets you point at a different model for whichever provider
is active, without a code change.
