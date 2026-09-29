from typing import Any

import psycopg
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


def test_mark_seen_reconnects_once_after_connection_is_lost(
    seen_store: PostgresSeenStore,
) -> None:
    original_conn = seen_store._conn
    original_conn.close()  # simulate a dropped connection

    seen_store.mark_seen("key-a", channel="discord")

    assert seen_store._conn is not original_conn
    assert seen_store.is_seen("key-a", channel="discord") is True


def test_is_seen_closes_the_old_connection_before_reconnecting(
    seen_store: PostgresSeenStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_conn = seen_store._conn

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise psycopg.OperationalError("connection lost")

    monkeypatch.setattr(original_conn, "execute", _boom)

    seen_store.is_seen("key-a", channel="discord")

    assert original_conn.closed


def test_is_seen_raises_when_reconnect_still_fails(
    seen_store: PostgresSeenStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken_conn = seen_store._conn

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise psycopg.OperationalError("still down")

    monkeypatch.setattr(broken_conn, "execute", _boom)
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: broken_conn)

    with pytest.raises(psycopg.OperationalError):
        seen_store.is_seen("key-a", channel="discord")
