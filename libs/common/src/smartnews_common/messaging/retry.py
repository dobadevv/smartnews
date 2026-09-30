from dataclasses import dataclass
from datetime import timedelta

from smartnews_common.messaging.topology import (
    DEFAULT_RETRY_DELAYS,
    dead_letter_queue_name,
    retry_queue_name,
)


@dataclass(frozen=True)
class RetryPolicy:
    delays: tuple[timedelta, ...] = DEFAULT_RETRY_DELAYS

    def is_final_attempt(self, attempt: int) -> bool:
        return attempt > len(self.delays)

    def failure_destination(self, queue: str, attempt: int) -> str:
        if self.is_final_attempt(attempt):
            return dead_letter_queue_name(queue)
        return retry_queue_name(queue, self.delays[attempt - 1])
