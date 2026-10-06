import pytest
from smartnews_common.timezones import validate_timezone


@pytest.mark.parametrize("timezone", ["Asia/Ho_Chi_Minh", "Asia/Kolkata", "UTC"])
def test_validate_timezone_returns_a_known_timezone_unchanged(timezone: str) -> None:
    assert validate_timezone(timezone) == timezone


@pytest.mark.parametrize(
    "timezone",
    [
        pytest.param("Not/AZone", id="unknown-zone"),
        pytest.param("", id="empty"),
        pytest.param("/etc/localtime", id="absolute-path"),
    ],
)
def test_validate_timezone_rejects_anything_that_is_not_a_known_zone(
    timezone: str,
) -> None:
    with pytest.raises(ValueError, match="unknown timezone"):
        validate_timezone(timezone)
