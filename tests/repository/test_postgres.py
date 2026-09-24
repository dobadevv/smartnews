from smartnews.repository.postgres import PostgresSeenStore


def test_filter_unseen_returns_all_keys_when_none_marked_seen(
    seen_store: PostgresSeenStore,
) -> None:
    unseen = seen_store.filter_unseen(["key-a", "key-b"], channel="discord")

    assert unseen == {"key-a", "key-b"}


def test_filter_unseen_excludes_keys_marked_seen_for_that_channel(
    seen_store: PostgresSeenStore,
) -> None:
    seen_store.mark_seen("key-a", channel="discord")

    unseen = seen_store.filter_unseen(["key-a", "key-b"], channel="discord")

    assert unseen == {"key-b"}


def test_mark_seen_is_scoped_per_channel(seen_store: PostgresSeenStore) -> None:
    seen_store.mark_seen("key-a", channel="discord")

    unseen_on_telegram = seen_store.filter_unseen(["key-a"], channel="telegram")

    assert unseen_on_telegram == {"key-a"}


def test_mark_seen_twice_does_not_raise(seen_store: PostgresSeenStore) -> None:
    seen_store.mark_seen("key-a", channel="discord")
    seen_store.mark_seen("key-a", channel="discord")

    unseen = seen_store.filter_unseen(["key-a"], channel="discord")

    assert unseen == set()
