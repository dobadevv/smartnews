from pathlib import Path

from crontab import CronTab

CRON_COMMENT = "smartnews-scheduled-run"


def install_cron_job(
    cron: CronTab,
    project_dir: Path,
    hour_utc: int,
    minute_utc: int,
    log_path: Path,
) -> None:
    command = f"cd {project_dir} && uv run smartnews >> {log_path} 2>&1"
    existing = list(cron.find_comment(CRON_COMMENT))
    job = existing[0] if existing else cron.new(command=command, comment=CRON_COMMENT)
    job.set_command(command)
    job.setall(minute_utc, hour_utc, "*", "*", "*")
    job.enable()


def remove_cron_job(cron: CronTab) -> None:
    cron.remove_all(comment=CRON_COMMENT)
