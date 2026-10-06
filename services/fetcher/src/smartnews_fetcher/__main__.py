import logging
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_fetcher.config import FetcherConfig, load_fetcher_config
from smartnews_fetcher.cycle import run_cycle
from smartnews_fetcher.loop import run_daily_at
from smartnews_fetcher.rss import RssFetcher

DEFAULT_CONFIG_PATH = Path("config/fetcher.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_fetcher_config(DEFAULT_CONFIG_PATH)
    run_one_cycle = partial(
        run_cycle,
        config=config,
        fetcher=RssFetcher(),
        engine=create_database_engine(require_env("DATABASE_URL")),
        rabbitmq_url=require_env("RABBITMQ_URL"),
    )
    stop_requested = threading.Event()
    call_on_shutdown_signals(stop_requested.set)
    zone = ZoneInfo(config.timezone)
    if config.run_once:
        logger.info(
            "fetcher started: %d enabled source(s), run_once=true, running a single cycle",
            sum(1 for source in config.sources if source.enabled),
        )
    else:
        logger.info(
            "fetcher started: %d enabled source(s), runs daily at %s %s",
            sum(1 for source in config.sources if source.enabled),
            config.run_at,
            config.timezone,
        )
    _start(
        run_one_cycle=run_one_cycle, config=config, zone=zone, stop_requested=stop_requested
    )
    logger.info("fetcher stopped")


def _start(
    run_one_cycle: Callable[[], int],
    config: FetcherConfig,
    zone: ZoneInfo,
    stop_requested: threading.Event,
) -> None:
    if config.run_once:
        _run_logged_cycle(run_one_cycle)
        return
    run_daily_at(
        lambda: _run_logged_cycle(run_one_cycle), config.run_at, zone, stop_requested
    )


def _run_logged_cycle(run_one_cycle: Callable[[], int]) -> None:
    published = run_one_cycle()
    logger.info("fetch cycle complete: published %d new article(s)", published)


if __name__ == "__main__":
    main()
