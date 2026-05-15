"""
Retry Decorator for Transient DB/Redis/HTTP Write Failures
===========================================================
P-06: Wrap write operations with configurable exponential-backoff retry.

Usage:
    from backend.utils.retry import with_retry
    from sqlalchemy.exc import OperationalError

    @with_retry(exceptions=(OperationalError,), max_attempts=3, backoff_seconds=0.5)
    def _bulk_upsert_node_metadata(db, items):
        ...

Rules:
  - Decorate INNER functions, NOT Celery task functions
    (Celery has its own self.retry() mechanism)
  - After max_attempts exhausted, the last exception is re-raised
  - Backoff uses exponential factor: wait = backoff_seconds * (backoff_factor ** attempt)
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Tuple, Type

logger = logging.getLogger(__name__)


def with_retry(
    exceptions: Tuple[Type[Exception], ...],
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    backoff_factor: float = 2.0,
):
    """
    Decorator factory. Retries the decorated function up to ``max_attempts`` times
    on any exception in ``exceptions``.

    Args:
        exceptions:       Tuple of exception types to catch and retry on.
        max_attempts:     Total number of attempts (1 = no retry).
        backoff_seconds:  Initial wait before first retry.
        backoff_factor:   Multiplier applied to wait on each subsequent retry.

    Raises:
        The last caught exception after all retries are exhausted.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        wait = backoff_seconds * (backoff_factor ** attempt)
                        logger.warning(
                            "with_retry: attempt %d/%d failed in %s — retrying in %.1fs: %s",
                            attempt + 1,
                            max_attempts,
                            fn.__qualname__,
                            wait,
                            exc,
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            "with_retry: all %d attempts exhausted in %s: %s",
                            max_attempts,
                            fn.__qualname__,
                            exc,
                        )
            raise last_exc
        return wrapper
    return decorator
