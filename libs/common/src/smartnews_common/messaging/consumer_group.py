import logging
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Protocol

logger = logging.getLogger(__name__)


class RunnableConsumer(Protocol):
    def run(self) -> None: ...

    def stop(self) -> None: ...

    def consume_one(self) -> None: ...


class ConsumerGroup:
    """Runs several blocking consumers side by side, one thread each.

    A consumer only returns when stopped, so the first one to finish, normally
    or by failing, takes the whole group down: a service must not keep running
    with one of its queues silently unconsumed.
    """

    def __init__(self, consumers: Sequence[RunnableConsumer]) -> None:
        self._consumers = tuple(consumers)

    def run(self) -> None:
        with ThreadPoolExecutor(max_workers=len(self._consumers)) as executor:
            futures = [executor.submit(consumer.run) for consumer in self._consumers]
            wait(futures, return_when=FIRST_COMPLETED)
            self.stop()
        for future in futures:
            future.result()

    def consume_one(self) -> None:
        """Let each consumer handle one message from its queue in turn, then return.

        Every consumer runs even if an earlier one fails; the first failure is
        re-raised at the end.
        """
        first_error: Exception | None = None
        for consumer in self._consumers:
            try:
                consumer.consume_one()
            except Exception as error:
                logger.exception("consuming one message failed")
                first_error = first_error or error
        if first_error is not None:
            raise first_error

    def stop(self) -> None:
        for consumer in self._consumers:
            consumer.stop()
