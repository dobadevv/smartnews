from typing import Protocol


class SeenStore(Protocol):
    def filter_unseen(self, keys: list[str], channel: str) -> set[str]:
        """Return the subset of `keys` not yet marked seen for `channel`."""
        ...

    def mark_seen(self, key: str, channel: str) -> None:
        """Record that `key` has been sent on `channel`."""
        ...
