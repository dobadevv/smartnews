from typing import Protocol


class SeenStore(Protocol):
    def is_seen(self, key: str, channel: str) -> bool:
        """Return whether `key` has already been sent on `channel`."""
        ...

    def mark_seen(self, key: str, channel: str) -> None:
        """Record that `key` has been sent on `channel`."""
        ...
