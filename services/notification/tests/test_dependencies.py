import tomllib
from pathlib import Path


def test_requests_is_declared_because_discord_sync_webhook_needs_it_at_runtime() -> None:
    """discord.SyncWebhook.from_url() lazily imports `requests`, and discord-py
    does not declare it as a dependency. The dev environment installs it
    transitively via `responses`, which masks a missing dependency here: a
    `--no-dev` production build crashes on startup with ModuleNotFoundError."""
    pyproject = tomllib.loads(
        (Path(__file__).parents[1] / "pyproject.toml").read_text()
    )
    dependency_names = {
        dependency.split("=")[0].split(">")[0].split("<")[0].strip()
        for dependency in pyproject["project"]["dependencies"]
    }

    assert "requests" in dependency_names
