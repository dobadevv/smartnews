import shutil
from pathlib import Path

import pytest
from crontab import CronTab

from smartnews.cronjob.installer import (
    CRON_COMMENT,
    build_cron_command,
    install_cron_job,
    remove_cron_job,
)


@pytest.fixture
def fake_uv_path(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    return "/usr/bin/uv"


def test_build_cron_command_uses_resolved_uv_path(fake_uv_path: str) -> None:
    command = build_cron_command(
        Path("/srv/smartnews"), Path("/srv/smartnews/logs/cron.log")
    )

    assert command == (
        f"cd /srv/smartnews && {fake_uv_path} run smartnews "
        ">> /srv/smartnews/logs/cron.log 2>&1"
    )


def test_build_cron_command_quotes_paths_containing_spaces(fake_uv_path: str) -> None:
    command = build_cron_command(
        Path("/srv/my project"), Path("/srv/my project/logs/cron.log")
    )

    assert command == (
        f"cd '/srv/my project' && {fake_uv_path} run smartnews "
        ">> '/srv/my project/logs/cron.log' 2>&1"
    )


def test_build_cron_command_raises_when_uv_not_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="uv"):
        build_cron_command(Path("/srv/smartnews"), Path("/srv/smartnews/logs/cron.log"))


def test_install_cron_job_creates_entry_with_given_schedule_and_command(
    fake_uv_path: str,
) -> None:
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
        f"cd /srv/smartnews && {fake_uv_path} run smartnews "
        ">> /srv/smartnews/logs/cron.log 2>&1" in line
    )


def test_install_cron_job_updates_existing_entry_instead_of_duplicating(
    fake_uv_path: str,
) -> None:
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


def test_install_cron_job_removes_stale_duplicate_entries(fake_uv_path: str) -> None:
    cron = CronTab(tab="")
    cron.new(command="echo stale-one", comment=CRON_COMMENT)
    cron.new(command="echo stale-two", comment=CRON_COMMENT)

    install_cron_job(
        cron,
        project_dir=Path("/srv/smartnews"),
        hour_utc=0,
        minute_utc=30,
        log_path=Path("/srv/smartnews/logs/cron.log"),
    )

    jobs = list(cron.find_comment(CRON_COMMENT))
    assert len(jobs) == 1
    assert str(jobs[0]).split()[:5] == ["30", "0", "*", "*", "*"]


def test_remove_cron_job_removes_existing_entry(fake_uv_path: str) -> None:
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
