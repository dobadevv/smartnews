import pytest

from smartnews_common.env import require_env


def test_require_env_returns_the_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMARTNEWS_TEST_VAR", "value")

    assert require_env("SMARTNEWS_TEST_VAR") == "value"


@pytest.mark.parametrize(
    "value",
    [pytest.param(None, id="unset"), pytest.param("", id="empty")],
)
def test_require_env_raises_naming_the_variable_when_missing(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("SMARTNEWS_TEST_VAR", raising=False)
    else:
        monkeypatch.setenv("SMARTNEWS_TEST_VAR", value)

    with pytest.raises(RuntimeError, match="SMARTNEWS_TEST_VAR"):
        require_env("SMARTNEWS_TEST_VAR")
