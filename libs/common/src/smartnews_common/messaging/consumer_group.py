from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Protocol


class RunnableConsumer(Protocol):
    def run(self) -> None: ...

    def stop(self) -> None: ...


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

    def stop(self) -> None:
        for consumer in self._consumers:
            consumer.stop()
