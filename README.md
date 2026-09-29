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
Fetcher(s) -> Aggregator -> Deduper (Postgres) -> Filter (LLM) -> Notifier(s) (Discord/Telegram)
```

Each run streams articles through this pipeline one at a time (an article
can be translated and sent before the next source is even fetched), rather
than loading everything into memory as one big batch:

1. **Fetch enabled sources** — every source in `config/sources.yaml` with
   `enabled: true` is fetched and parsed into articles. If a source fails
   to fetch, it's logged and skipped for this run; every other source is
   unaffected, and the failing one is retried on the next run.
2. **Drop stale articles** — articles older than the source's
   `lookback_days` (default 7) are dropped before any database lookup or
   LLM call, since there's no point spending either on something that's
   already stale.
3. **Dedup + cap** — for each remaining article, it's kept only if it's
   still unseen on at least one enabled channel *and* its source hasn't
   yet hit its configured `max_posts` for this run. This keeps a single
   noisy source from drowning out the others while still draining its
   backlog over successive runs.
4. **Filter/translate** — each surviving article is passed once through
   the configured LLM filter (or left as-is if the filter is disabled). A
   failed LLM call is logged and the article is kept with its original
   title/summary instead of being dropped.
5. **Notify** — for every enabled channel, the article is dedup-checked
   again (this time against that specific channel), sent, and only marked
   as seen on that channel once the send succeeds. If sending fails, the
   article stays eligible for a retry on the next run instead of being
   silently lost.

If no notifier is enabled, the pipeline still runs end-to-end and prints
surviving articles to stdout, so you can try it out without setting up
Discord/Telegram or Postgres first.

Each run processes one batch and exits — there is no built-in scheduler,
so recurring execution (e.g. every 30 minutes) is handled by an external
scheduler such as `cron`, a systemd timer, or a container orchestrator's
job scheduling.

## Usage

### Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A Postgres database (only required if at least one notifier is enabled)

### Installation

```bash
uv sync
```

### Configuration

`config/sources.yaml` lists the RSS sources to fetch, and controls which
notifiers and which LLM filter are active:

```yaml
sources:
  - name: example-blog
    url: https://example.com/feed.xml
    enabled: true
    max_posts: 1        # optional; cap on new sends per source per run
    lookback_days: 7     # optional; default 7

notifiers:
  discord:
    enabled: false
  telegram:
    enabled: false

filter:
  enabled: false
  provider: gemini            # "gemini" (default) or "groq"
  model: gemini-3.8-flash     # optional; defaults to the provider's own default
```

Only sources with `enabled: true` are fetched.

Credentials are never stored in this file — they're read from environment
variables at startup, only for whichever channels/providers are enabled.
Copy `.env.example` to `.env` and fill in what you need:

```bash
cp .env.example .env
```

| Variable              | Required when                                      |
|-----------------------|-----------------------------------------------------|
| `DATABASE_URL`        | At least one notifier is enabled                     |
| `DISCORD_WEBHOOK_URL` | `notifiers.discord.enabled: true`                    |
| `TELEGRAM_BOT_TOKEN`  | `notifiers.telegram.enabled: true`                   |
| `TELEGRAM_CHAT_ID`    | `notifiers.telegram.enabled: true`                   |
| `GEMINI_API_KEY`      | `filter.enabled: true` and `filter.provider: gemini` |
| `GROQ_API_KEY`        | `filter.enabled: true` and `filter.provider: groq`   |

Free-tier keys: [Gemini](https://aistudio.google.com/apikey),
[Groq](https://console.groq.com/keys). Groq's free tier has noticeably
higher rate limits than Gemini's, which can help if a large fetch batch
exhausts Gemini's free-tier quota.

### Running

```bash
uv run smartnews
```

This runs one full pipeline pass (fetch → dedup → filter → notify) and
exits. To run it continuously, schedule this command with `cron`, a
systemd timer, or your platform's job scheduler at whatever interval you
want (e.g. every 30 minutes).

### Development

```bash
uv run pytest       # run the test suite
uv run ruff check    # lint
```
