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
- **Repository (dedup store)** — checks whether an article (by URL hash)
  has already been sent, and records new sends. Backed by Postgres.
- **Filter** — takes a list of articles and returns the subset (optionally
  summarized) that should be forwarded. Default is a no-op pass-through;
  another implementation will call an LLM to classify/summarize
  (provider not decided yet — kept behind the interface).
- **Notifier** — sends a list of articles to a destination channel.
  Implementations: `DiscordNotifier` (webhook), `TelegramNotifier` (bot
  API). Which notifier(s) are active is controlled by config.
- **Pipeline** — orchestrates one fetch -> dedup -> filter -> send cycle
  using whichever implementations are wired in.
- **Scheduler** — runs the pipeline on a configured interval, keeping the
  process alive as a long-running service.

## File Organization

```
src/smartnews/
  config.py           # load & validate config.yaml (pydantic models)
  models.py            # Article domain model
  fetching/
    base.py            # Fetcher interface
    rss.py              # feedparser-based implementation
  repository/
    base.py            # Repository interface (dedup store)
    postgres.py         # Postgres implementation
  filtering/
    base.py            # Filter interface
    passthrough.py      # no-op filter (default)
  notifiers/
    base.py            # Notifier interface
    discord.py
    telegram.py
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
   c. Dedup: look up each article's URL hash in Postgres; drop ones
      already sent.
   d. Filter: run the remaining articles through the configured
      `Filter` implementation.
   e. Send: pass the surviving articles to each active `Notifier`.
   f. Record: mark the sent articles as seen in Postgres.
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

Only sources with `enabled: true` are fetched. Notifier and filter
settings will be added to this file as those stages are implemented.
