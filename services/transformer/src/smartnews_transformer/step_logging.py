import logging
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def logged_step(step: str, article_id: int) -> Iterator[None]:
    """Log whether one processing step of an article succeeded or failed.

    A failure is re-raised so the consumer's retry ladder still sees it; the
    consumer logs the traceback, so only the error itself is logged here.
    """
    try:
        yield
    except Exception as error:
        logger.error("%s failed: article_id=%d error=%s", step, article_id, error)
        raise
    logger.info("%s succeeded: article_id=%d", step, article_id)
