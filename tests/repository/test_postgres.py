from typing import Any

import pytest

from smartnews.repository.postgres import PostgresSeenStore


def test_is_seen_returns_false_when_key_never_marked_seen(
    seen_store: PostgresSeenStore,
) -> None:
    assert seen_store.is_seen("key-a", channel="discord") is False


def test_is_seen_returns_true_after_mark_seen(seen_store: PostgresSeenStore) -> None:
    seen_store.mark_seen("key-a", channel="discord")

    assert seen_store.is_seen("key-a", channel="discord") is True


def test_mark_seen_is_scoped_per_channel(seen_store: PostgresSeenStore) -> None:
    seen_store.mark_seen("key-a", channel="discord")

    assert seen_store.is_seen("key-a", channel="telegram") is False


def test_mark_seen_twice_does_not_raise(seen_store: PostgresSeenStore) -> None:
    seen_store.mark_seen("key-a", channel="discord")
    seen_store.mark_seen("key-a", channel="discord")

    assert seen_store.is_seen("key-a", channel="discord") is True


def test_is_seen_reconnects_once_after_connection_is_lost(
    seen_store: PostgresSeenStore,
) -> None:
    seen_store.mark_seen("key-a", channel="discord")
    original_conn = seen_store._conn
    original_conn.close()  # simulate a dropped connection

    result = seen_store.is_seen("key-a", channel="discord")

    assert result is True
    assert seen_store._conn is not original_conn


def test_is_seen_raises_non_connection_errors_without_reconnecting(
    seen_store: PostgresSeenStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_conn = seen_store._conn

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise ValueError("not a connection problem")

    monkeypatch.setattr(original_conn, "execute", _boom)

    with pytest.raises(ValueError):
        seen_store.is_seen("key-a", channel="discord")

    assert seen_store._conn is original_conn
