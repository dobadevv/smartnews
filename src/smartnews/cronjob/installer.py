import shlex
import shutil
from pathlib import Path

from crontab import CronTab

CRON_COMMENT = "smartnews-scheduled-run"


def build_cron_command(project_dir: Path, log_path: Path) -> str:
    uv_path = shutil.which("uv")
    if uv_path is None:
        raise RuntimeError(
            "`uv` was not found on PATH; cannot install a crontab entry that runs it"
        )
    return (
        f"cd {shlex.quote(str(project_dir))} && "
        f"{shlex.quote(uv_path)} run smartnews >> {shlex.quote(str(log_path))} 2>&1"
    )


def install_cron_job(
    cron: CronTab,
    project_dir: Path,
    hour_utc: int,
    minute_utc: int,
    log_path: Path,
) -> None:
    command = build_cron_command(project_dir, log_path)
    existing = list(cron.find_comment(CRON_COMMENT))
    for stale in existing[1:]:
        cron.remove(stale)
    job = existing[0] if existing else cron.new(command=command, comment=CRON_COMMENT)
    job.set_command(command)
    job.setall(minute_utc, hour_utc, "*", "*", "*")
    job.enable()


def remove_cron_job(cron: CronTab) -> None:
    cron.remove_all(comment=CRON_COMMENT)
