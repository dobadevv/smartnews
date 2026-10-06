from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_timezone(timezone: str) -> str:
    try:
        ZoneInfo(timezone)
    # ZoneInfo raises ValueError instead of ZoneInfoNotFoundError for keys
    # that are not relative paths, such as an empty string.
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"unknown timezone: {timezone}") from error
    return timezone
