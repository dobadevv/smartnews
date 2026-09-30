FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

# Selects what to install: a service (`--no-dev --package smartnews-fetcher`)
# or the migration tooling (`--only-group migrate`).
ARG UV_SYNC_ARGS
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app
COPY . .
RUN uv sync --frozen ${UV_SYNC_ARGS}
ENV PATH="/app/.venv/bin:${PATH}"
