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
  **on a given channel** (`is_seen(key, channel) -> bool`), and records
  new sends (`mark_seen`). Backed by Postgres, with a `(key, channel)`
  unique constraint so the same article can be independently tracked per
  Discord/Telegram. `PostgresSeenStore` is a context manager that opens
  one connection for the whole pipeline run (not one per call) and
  reconnects once, transparently, if that connection drops mid-run. An
  article is only marked seen for a channel after it has actually been
  sent there — if sending fails, it stays eligible for a retry on the
  next cycle instead of being silently dropped.
- **Filter** — takes one article and returns the (possibly rewritten)
  article that should be forwarded; called once per article as it streams
  through the pipeline. Default is `PassthroughFilter` (no-op).
  `GeminiFilter` and `GroqFilter` both call a free-tier LLM API to rewrite
  the article's title/summary: translated to Vietnamese, technical terms
  (product names, languages, frameworks, acronyms like API/LLM/SDK) left
  untranslated, and the summary rewritten as a brief 1-2 sentence
  overview; both share the same prompt via `filtering/prompts.py`. A
  failed call is logged and the article is kept with its original
  title/summary rather than dropped — this failure is isolated per
  article and never affects the next one. `filtering/factory.py` builds
  the active `Filter` from config + env (dispatching on `filter.provider`),
  same pattern as notifiers.
- **Notifier** — sends one article to a destination channel.
  Implementations: `DiscordNotifier` (webhook), `TelegramNotifier` (bot
  API). Which notifier(s) are active is controlled by
  `notifiers.<channel>.enabled` in `config/sources.yaml`; credentials
  (webhook URL, bot token, chat id) come from environment variables, not
  the YAML file, so they never get committed. `notifiers/factory.py`
  builds the active `Notifier` list from config + env, raising a clear
  error if a channel is enabled but its env vars are missing.
- **Pipeline** — a chain of generator functions that streams each article
  through fetch -> dedup-check -> filter -> notifier-dispatch
  individually, rather than passing whole-batch lists between stages. An
  article is translated and sent to every applicable notifier before the
  next article is even fetched; a fetch failure on one source, an LLM
  failure on one article, or a send failure on one notifier is isolated
  and does not stop the rest of the stream. `main()` currently falls back
  to printing articles to stdout when no notifier is enabled, so the
  service still runs without any external setup.
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
  pipeline.py           # generator streaming pipeline: fetch -> dedup -> filter -> send, one article at a time
  scheduler.py           # runs the pipeline on an interval
  __init__.py            # main() entrypoint / service bootstrap
config/
  sources.yaml            # list of RSS sources (name, url, enabled)
```

## Program Flow

1. `main()` loads `config/sources.yaml` (sources, notifier settings,
   filter settings, poll interval).
2. The scheduler starts and, on each tick, streams articles through a
   chain of generators (`pipeline.py`) instead of building intermediate
   lists — an article can be translated and sent before the next source
   is even fetched:
   a. `stream_enabled_sources`: for every source with `enabled: true`,
      fetch its feed and parse entries into `Article` objects — no
      capping yet. If fetching a source raises, that source is logged and
      skipped; articles already streamed from earlier sources in the same
      cycle are unaffected, and the failing source is retried next cycle.
      If no notifier is enabled, articles go straight to
      `stream_translated` and are printed to stdout — there's no dedup
      store to check against, and no cap, in this fallback mode.
   b. `stream_unseen_for_any_channel`: for each article, keep it only if
      it's still unseen on at least one enabled channel (union across
      notifiers), so the filter never re-translates an article every
      channel has already received.
   c. `stream_capped_to_minimum_posts`: cap each source's *still-unseen*
      articles to its configured `minimum_posts`, so it acts as a
      backlog-draining floor — once a source's newest item has been sent,
      the next-oldest unsent item from that source surfaces on the next
      cycle instead of the source going silent. Capping runs after dedup
      (not before) precisely so already-sent items don't consume the cap.
   d. `stream_translated`: run each still-unseen, capped article through
      the configured `Filter` implementation, one call per article.
   e. `run_notify_pipeline`: for each translated article, loop over every
      active `Notifier` (its own channel, e.g. `"discord"`, `"telegram"`):
      i. Dedup again: ask the `SeenStore` whether this article's key is
         seen on *this specific* channel — step (b) only guarantees
         unseen on at least one channel, not this one.
      ii. Send: pass the article to this notifier; a failure is logged
          and isolated to that notifier/article pair.
      iii. Record: if the send succeeded, mark the article seen on this
           channel in Postgres.
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
