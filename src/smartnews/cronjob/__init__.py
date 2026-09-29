import logging
from pathlib import Path

from crontab import CronTab

from smartnews import DEFAULT_CONFIG_PATH
from smartnews.config import load_cronjob
from smartnews.cronjob.base import compute_utc_schedule
from smartnews.cronjob.installer import install_cron_job, remove_cron_job

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    cronjob_config = load_cronjob(DEFAULT_CONFIG_PATH)
    project_dir = Path.cwd()
    cron = CronTab(user=True)

    if not cronjob_config.enabled:
        remove_cron_job(cron)
        cron.write()
        logger.info("cronjob disabled in config; removed any existing crontab entry")
        return

    hour_utc, minute_utc = compute_utc_schedule(
        cronjob_config.time, cronjob_config.timezone
    )
    log_path = project_dir / "logs" / "cron.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    install_cron_job(cron, project_dir, hour_utc, minute_utc, log_path)
    cron.write()

    logger.info(
        "installed crontab entry: %s %s -> %02d:%02d UTC daily",
        cronjob_config.time,
        cronjob_config.timezone,
        hour_utc,
        minute_utc,
    )


def remove() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    cron = CronTab(user=True)
    remove_cron_job(cron)
    cron.write()

    logger.info("removed any existing smartnews crontab entry")
