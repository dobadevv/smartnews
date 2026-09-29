from pathlib import Path

from crontab import CronTab

from smartnews.cronjob.installer import CRON_COMMENT, install_cron_job, remove_cron_job


def test_install_cron_job_creates_entry_with_given_schedule_and_command() -> None:
    cron = CronTab(tab="")

    install_cron_job(
        cron,
        project_dir=Path("/srv/smartnews"),
        hour_utc=0,
        minute_utc=30,
        log_path=Path("/srv/smartnews/logs/cron.log"),
    )

    jobs = list(cron.find_comment(CRON_COMMENT))
    assert len(jobs) == 1
    line = str(jobs[0])
    assert line.split()[:5] == ["30", "0", "*", "*", "*"]
    assert (
        "cd /srv/smartnews && uv run smartnews >> /srv/smartnews/logs/cron.log 2>&1"
        in line
    )


def test_install_cron_job_updates_existing_entry_instead_of_duplicating() -> None:
    cron = CronTab(tab="")
    install_cron_job(
        cron,
        project_dir=Path("/srv/smartnews"),
        hour_utc=0,
        minute_utc=30,
        log_path=Path("/srv/smartnews/logs/cron.log"),
    )

    install_cron_job(
        cron,
        project_dir=Path("/srv/smartnews"),
        hour_utc=1,
        minute_utc=45,
        log_path=Path("/srv/smartnews/logs/cron.log"),
    )

    jobs = list(cron.find_comment(CRON_COMMENT))
    assert len(jobs) == 1
    assert str(jobs[0]).split()[:5] == ["45", "1", "*", "*", "*"]


def test_remove_cron_job_removes_existing_entry() -> None:
    cron = CronTab(tab="")
    install_cron_job(
        cron,
        project_dir=Path("/srv/smartnews"),
        hour_utc=0,
        minute_utc=0,
        log_path=Path("/srv/smartnews/logs/cron.log"),
    )

    remove_cron_job(cron)

    assert list(cron.find_comment(CRON_COMMENT)) == []


def test_remove_cron_job_is_safe_when_no_entry_exists() -> None:
    cron = CronTab(tab="")

    remove_cron_job(cron)

    assert list(cron.find_comment(CRON_COMMENT)) == []
