import logging
import threading
from collections.abc import Callable
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.signals import call_on_shutdown_signals

from smartnews_redriver.config import RedriverConfig, load_redriver_config
from smartnews_redriver.redrive import run_redrive_pass
from smartnews_redriver.schedule import run_hourly

DEFAULT_CONFIG_PATH = Path("config/redriver.yaml")

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    config = load_redriver_config(DEFAULT_CONFIG_PATH)
    stop_requested = threading.Event()
    redrive_pass = partial(
        run_redrive_pass,
        rabbitmq_url=require_env("RABBITMQ_URL"),
        queues=config.queues,
        delay_seconds=config.delay_seconds,
        stop_requested=stop_requested,
        max_messages_per_run=config.max_messages_per_run,
    )
    call_on_shutdown_signals(stop_requested.set)
    if config.run_once:
        logger.info(
            "redriver started: queues %s, run_once=true, running a single pass",
            config.queues,
        )
    else:
        logger.info(
            "redriver started: queues %s, runs at the top of every hour (%s)",
            config.queues,
            config.timezone,
        )
    _start(
        redrive_pass=redrive_pass,
        config=config,
        zone=ZoneInfo(config.timezone),
        stop_requested=stop_requested,
    )
    logger.info("redriver stopped")


def _start(
    redrive_pass: Callable[[], None],
    config: RedriverConfig,
    zone: ZoneInfo,
    stop_requested: threading.Event,
) -> None:
    if config.run_once:
        redrive_pass()
        return
    run_hourly(redrive_pass=redrive_pass, zone=zone, stop_requested=stop_requested)


if __name__ == "__main__":
    main()
