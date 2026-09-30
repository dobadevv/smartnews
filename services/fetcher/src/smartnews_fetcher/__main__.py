import logging
import threading
from pathlib import Path
from zoneinfo import ZoneInfo

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_fetcher.config import load_fetcher_config
from smartnews_fetcher.cycle import CycleDeps, run_cycle
from smartnews_fetcher.loop import run_daily_at
from smartnews_fetcher.rss import RssFetcher

DEFAULT_CONFIG_PATH = Path("config/fetcher.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_fetcher_config(DEFAULT_CONFIG_PATH)
    deps = CycleDeps(
        config=config,
        fetcher=RssFetcher(),
        engine=create_database_engine(require_env("DATABASE_URL")),
        rabbitmq_url=require_env("RABBITMQ_URL"),
    )
    stop_requested = threading.Event()
    call_on_shutdown_signals(stop_requested.set)
    zone = ZoneInfo(config.timezone)
    logger.info(
        "fetcher started: %d enabled source(s), runs daily at %s %s",
        sum(1 for source in config.sources if source.enabled),
        config.run_at,
        config.timezone,
    )
    run_daily_at(lambda: _run_logged_cycle(deps), config.run_at, zone, stop_requested)
    logger.info("fetcher stopped")


def _run_logged_cycle(deps: CycleDeps) -> None:
    published = run_cycle(deps)
    logger.info("fetch cycle complete: published %d new article(s)", published)


if __name__ == "__main__":
    main()
