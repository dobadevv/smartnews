import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from smartnews_common.db.engine import create_database_engine
from smartnews_common.env import require_env
from smartnews_common.logging_config import configure_logging
from smartnews_common.messaging.topology import ARTICLES_FETCHED
from smartnews_common.signals import call_on_shutdown_signals
from sqlalchemy import Engine

from smartnews_redriver.config import RedriverConfig, load_redriver_config
from smartnews_redriver.redrive import run_redrive_pass
from smartnews_redriver.retransform import run_retransform_pass
from smartnews_redriver.schedule import run_hourly

DEFAULT_CONFIG_PATH = Path("config/redriver.yaml")
REDRIVE_JOB = "redrive"
RETRANSFORM_JOB = "retransform"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    name: str
    run_pass: Callable[[], None]


def main() -> None:
    configure_logging()
    config = load_redriver_config(DEFAULT_CONFIG_PATH)
    stop_requested = threading.Event()
    call_on_shutdown_signals(stop_requested.set)
    rabbitmq_url = require_env("RABBITMQ_URL")
    _log_startup(config)
    jobs = [
        _redrive_job(
            config=config, rabbitmq_url=rabbitmq_url, stop_requested=stop_requested
        )
    ]
    engine: Engine | None = None
    if config.retransform.enabled:
        engine = create_database_engine(require_env("DATABASE_URL"))
        jobs.append(
            _retransform_job(
                config=config,
                engine=engine,
                rabbitmq_url=rabbitmq_url,
                stop_requested=stop_requested,
            )
        )
    try:
        _start(
            jobs=jobs,
            config=config,
            zone=ZoneInfo(config.timezone),
            stop_requested=stop_requested,
        )
    finally:
        if engine is not None:
            engine.dispose()
    logger.info("redriver stopped")


def _redrive_job(
    config: RedriverConfig, rabbitmq_url: str, stop_requested: threading.Event
) -> Job:
    return Job(
        name=REDRIVE_JOB,
        run_pass=partial(
            run_redrive_pass,
            rabbitmq_url=rabbitmq_url,
            queues=config.queues,
            delay_seconds=config.delay_seconds,
            stop_requested=stop_requested,
            max_messages_per_run=config.max_messages_per_run,
        ),
    )


def _retransform_job(
    config: RedriverConfig,
    engine: Engine,
    rabbitmq_url: str,
    stop_requested: threading.Event,
) -> Job:
    return Job(
        name=RETRANSFORM_JOB,
        run_pass=partial(
            run_retransform_pass,
            engine=engine,
            rabbitmq_url=rabbitmq_url,
            min_age_minutes=config.retransform.min_age_minutes,
            delay_seconds=config.delay_seconds,
            max_messages_per_run=config.max_messages_per_run,
            stop_requested=stop_requested,
        ),
    )


def _log_startup(config: RedriverConfig) -> None:
    if config.run_once:
        logger.info(
            "redriver started: queues %s, run_once=true, running a single pass of each job",
            config.queues,
        )
    else:
        logger.info(
            "redriver started: queues %s, runs at the top of every hour (%s)",
            config.queues,
            config.timezone,
        )
    if config.retransform.enabled:
        logger.info(
            "retransform enabled: republishes articles untranslated for at least"
            " %d minute(s) to %s",
            config.retransform.min_age_minutes,
            ARTICLES_FETCHED,
        )
    else:
        logger.info("retransform disabled")


def _start(
    jobs: list[Job],
    config: RedriverConfig,
    zone: ZoneInfo,
    stop_requested: threading.Event,
) -> None:
    threads = [
        _JobThread(job=job, config=config, zone=zone, stop_requested=stop_requested)
        for job in jobs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # Re-raising in start order makes the process exit non-zero in run_once
    # mode; every failure was already logged by its own thread.
    for thread in threads:
        if thread.error is not None:
            raise thread.error


class _JobThread(threading.Thread):
    """Runs one job, hourly or once, and keeps a run-once failure for the caller."""

    def __init__(
        self,
        job: Job,
        config: RedriverConfig,
        zone: ZoneInfo,
        stop_requested: threading.Event,
    ) -> None:
        super().__init__(name=f"{job.name}-job")
        self._job = job
        self._config = config
        self._zone = zone
        self._stop_requested = stop_requested
        self.error: Exception | None = None

    def run(self) -> None:
        if not self._config.run_once:
            run_hourly(
                run_pass=self._job.run_pass,
                job_name=self._job.name,
                zone=self._zone,
                stop_requested=self._stop_requested,
            )
            return
        try:
            self._job.run_pass()
        except Exception as error:
            logger.exception("%s pass failed", self._job.name)
            self.error = error


if __name__ == "__main__":
    main()
