from datetime import timedelta

import pytest
from smartnews_common.messaging.retry import RetryPolicy


@pytest.mark.parametrize(
    ("attempt", "want"),
    [
        pytest.param(1, "articles.fetched.retry.1m", id="first failure waits 1m"),
        pytest.param(2, "articles.fetched.retry.5m", id="second failure waits 5m"),
        pytest.param(3, "articles.fetched.retry.15m", id="third failure waits 15m"),
        pytest.param(4, "articles.fetched.dlq", id="fourth failure is dead-lettered"),
    ],
)
def test_failure_destination_walks_the_retry_ladder(attempt: int, want: str) -> None:
    assert RetryPolicy().failure_destination("articles.fetched", attempt) == want


@pytest.mark.parametrize(
    ("attempt", "want"),
    [
        pytest.param(1, False, id="first attempt"),
        pytest.param(3, False, id="third attempt"),
        pytest.param(4, True, id="fourth attempt, all retries used"),
    ],
)
def test_is_final_attempt_is_true_only_once_all_retries_are_used(attempt: int, want: bool) -> None:
    assert RetryPolicy().is_final_attempt(attempt) is want


def test_retry_queue_names_use_seconds_for_sub_minute_delays() -> None:
    policy = RetryPolicy(delays=(timedelta(seconds=1),))

    assert policy.failure_destination("q", 1) == "q.retry.1s"
    assert policy.failure_destination("q", 2) == "q.dlq"
