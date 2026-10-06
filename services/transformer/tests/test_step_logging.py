import logging

import pytest
from smartnews_transformer.step_logging import logged_step


def test_logged_step_logs_the_article_id_when_the_step_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO), logged_step("translate summary", article_id=5):
        pass

    [record] = caplog.records
    assert record.levelno == logging.INFO
    assert record.getMessage() == "translate summary succeeded: article_id=5"


def test_logged_step_logs_and_reraises_when_the_step_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.INFO),
        pytest.raises(RuntimeError, match="boom"),
        logged_step("save transformation", article_id=5),
    ):
        raise RuntimeError("boom")

    [record] = caplog.records
    assert record.levelno == logging.ERROR
    assert record.getMessage() == "save transformation failed: article_id=5 error=boom"
