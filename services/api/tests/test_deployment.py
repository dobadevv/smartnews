from pathlib import Path

import yaml


def test_compose_runs_the_api_with_several_gunicorn_workers() -> None:
    """Gunicorn defaults to one sync worker, so a single slow request would
    stall every other request from the frontend."""
    compose = yaml.safe_load((Path(__file__).parents[3] / "docker-compose.yaml").read_text())
    command = compose["services"]["api"]["command"]

    assert "--workers" in command
    assert int(command[command.index("--workers") + 1]) > 1
