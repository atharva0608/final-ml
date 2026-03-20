"""
Distributed Locks Service (Enterprise Remediation Phase 8)
===========================================================

Distributed concurrency control using Redis.

Features:
- NX EX locks (SET key value NX EX 120)
- Heartbeat-extended locks (HeartbeatLock) — extends TTL while work runs
- Atomic Lua rate limiting
- Lock expiration to prevent permanent deadlock
- Circuit breaker persistence

Enterprise Guardrails:
- All locks MUST expire (prevent permanent deadlock on worker crash)
- Lock keys: lock:substitute:{cluster_id}, lock:pool:{pool_id}, lock:circuit:{service}
- DB is source of truth for circuit breaker state (Redis sync on startup)
- HeartbeatLock: heartbeat thread renews TTL every timeout/2 seconds.
  If Redis connection drops, heartbeat sets stop_event to signal the main thread.
"""
import logging
import threading
import time as _time
from typing import Optional, Callable, Any
from contextlib import contextmanager
from redis import Redis, ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session

from backend.core.redis_client import get_redis_client
from backend.core.logger import logger
from backend.models.circuit_breaker_state import CircuitBreakerState
from datetime import datetime


class DistributedLock:
    """
    Distributed lock using Redis NX EX.

    Prevents split-brain actions across multiple workers.
    """

    DEFAULT_TIMEOUT = 120  # 2 minutes
    DEFAULT_RETRY_DELAY = 0.1  # 100ms

    def __init__(self, redis: Redis, lock_key: str, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize distributed lock.

        Args:
            redis: Redis client
            lock_key: Lock key (e.g., "lock:substitute:{cluster_id}")
            timeout: Lock expiration in seconds (MUST be set to prevent permanent deadlock)
        """
        self.redis = redis
        self.lock_key = lock_key
        self.timeout = timeout
        self.lock_id = None

    def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """
        Acquire distributed lock.

        Args:
            blocking: If True, block until lock is acquired
            timeout: Max time to wait for lock (None = wait forever)

        Returns:
            True if lock acquired, False otherwise
        """
        import uuid
        import time

        self.lock_id = str(uuid.uuid4())
        end_time = time.time() + timeout if timeout else None

        while True:
            # Try to acquire lock using NX EX
            acquired = self.redis.set(
                self.lock_key,
                self.lock_id,
                nx=True,  # Only set if not exists
                ex=self.timeout  # Expire after timeout seconds
            )

            if acquired:
                logger.debug(f"Acquired lock: {self.lock_key} (timeout={self.timeout}s)")
                return True

            if not blocking:
                return False

            if end_time and time.time() > end_time:
                logger.warning(f"Lock acquisition timeout: {self.lock_key}")
                return False

            # Wait before retry
            time.sleep(self.DEFAULT_RETRY_DELAY)

    def release(self):
        """
        Release distributed lock.

        Only releases if lock_id matches (prevents releasing someone else's lock).
        """
        if not self.lock_id:
            return

        # Lua script to atomically check and delete lock
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        released = self.redis.eval(lua_script, 1, self.lock_key, self.lock_id)

        if released:
            logger.debug(f"Released lock: {self.lock_key}")
        else:
            logger.warning(f"Lock already expired or owned by another process: {self.lock_key}")

        self.lock_id = None

    def extend_ttl(self, extra_seconds: int = None) -> bool:
        """
        Extend the TTL of the lock by resetting it to the original timeout.
        Uses a Lua script to only extend if we still own the lock.

        Returns True if extension succeeded, False if lock was lost.
        """
        if not self.lock_id:
            return False
        ttl = extra_seconds or self.timeout
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        try:
            result = self.redis.eval(lua_script, 1, self.lock_key, self.lock_id, ttl)
            return bool(result)
        except Exception as e:
            logger.warning(f"[DistributedLock] extend_ttl failed for {self.lock_key}: {e}")
            return False

    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError(f"Failed to acquire lock: {self.lock_key}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


class HeartbeatLock:
    """
    Distributed lock with a background heartbeat thread that extends TTL
    while the holder is still running.

    Use this for long-running Celery tasks where the task can exceed the
    lock TTL before completing.

    Usage:
        stop_event = threading.Event()
        lock = HeartbeatLock(redis, "lock:key", timeout=300, stop_event=stop_event)
        if lock.acquire():
            try:
                # Long-running work here.
                # Check stop_event.is_set() between major operations.
                while not stop_event.is_set():
                    do_work()
            finally:
                lock.release()

    The heartbeat thread renews the lock TTL every timeout/2 seconds.
    If Redis connection drops, the heartbeat sets stop_event to signal abort.
    """

    def __init__(
        self,
        redis: Redis,
        lock_key: str,
        timeout: int = 300,
        stop_event: Optional[threading.Event] = None,
    ):
        self.redis = redis
        self.lock_key = lock_key
        self.timeout = timeout
        self.stop_event = stop_event or threading.Event()
        self._lock = DistributedLock(redis, lock_key, timeout)
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_stop = threading.Event()

    def acquire(self, blocking: bool = True, wait_timeout: Optional[int] = None) -> bool:
        """Acquire the lock and start the heartbeat thread."""
        acquired = self._lock.acquire(blocking=blocking, timeout=wait_timeout)
        if acquired:
            self._start_heartbeat()
        return acquired

    def release(self):
        """Stop heartbeat thread and release the lock."""
        self._stop_heartbeat()
        self._lock.release()

    def _start_heartbeat(self):
        """Start background thread that renews lock TTL every timeout/2 seconds."""
        self._heartbeat_stop.clear()
        interval = max(1, self.timeout // 2)

        def _heartbeat_loop():
            while not self._heartbeat_stop.wait(timeout=interval):
                try:
                    extended = self._lock.extend_ttl(self.timeout)
                    if not extended:
                        logger.warning(
                            f"[HeartbeatLock] Lost lock {self.lock_key} — "
                            f"signalling main thread to abort"
                        )
                        self.stop_event.set()
                        return
                    logger.debug(f"[HeartbeatLock] Renewed {self.lock_key} TTL (+{self.timeout}s)")
                except RedisConnectionError as ce:
                    logger.error(
                        f"[HeartbeatLock] Redis connection lost for {self.lock_key}: {ce} "
                        f"— signalling main thread to abort"
                    )
                    self.stop_event.set()
                    return
                except Exception as e:
                    logger.warning(f"[HeartbeatLock] Heartbeat error for {self.lock_key}: {e}")

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            daemon=True,
            name=f"heartbeat-{self.lock_key}",
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        """Signal and join the heartbeat thread."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Failed to acquire HeartbeatLock: {self.lock_key}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


class AtomicRateLimiter:
    """
    Atomic rate limiter using Redis Lua scripts.

    Prevents race conditions in incr/expire operations.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    def is_rate_limited(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> bool:
        """
        Check if rate limit is exceeded.

        Uses Lua script to atomically increment counter and set expiration.

        Args:
            key: Rate limit key (e.g., "rate:dryrun:{region}")
            limit: Max count in window
            window_seconds: Time window in seconds

        Returns:
            True if rate limited, False otherwise
        """
        # Lua script to atomically increment and expire
        lua_script = """
        local current = redis.call("incr", KEYS[1])
        if current == 1 then
            redis.call("expire", KEYS[1], ARGV[1])
        end
        return current
        """

        current_count = self.redis.eval(
            lua_script,
            1,
            key,
            window_seconds
        )

        is_limited = current_count > limit

        if is_limited:
            logger.warning(f"Rate limit exceeded: {key} ({current_count}/{limit})")

        return is_limited

    def get_remaining(
        self,
        key: str,
        limit: int
    ) -> int:
        """
        Get remaining requests in current window.

        Args:
            key: Rate limit key
            limit: Max count in window

        Returns:
            Remaining count (0 if rate limited)
        """
        current = int(self.redis.get(key) or 0)
        remaining = max(0, limit - current)
        return remaining


class CircuitBreakerService:
    """
    Circuit breaker with DB persistence.

    Enterprise Guardrail:
    - DB is source of truth for circuit breaker state
    - On service startup, load state from DB to Redis
    - Sync to DB on every state change
    - Prevents Redis flush from resetting tripped breakers
    """

    STATES = ["CLOSED", "OPEN", "HALF_OPEN"]
    DEFAULT_FAILURE_THRESHOLD = 5
    DEFAULT_TIMEOUT = 60  # 60 seconds before auto half-open

    def __init__(self, db: Session, redis: Redis, service_name: str):
        """
        Initialize circuit breaker.

        Args:
            db: Database session
            redis: Redis client
            service_name: Service name (e.g., "karpenter", "substitute_manager")
        """
        self.db = db
        self.redis = redis
        self.service_name = service_name
        self.redis_key = f"circuit:{service_name}"

        # Load initial state from DB
        self._load_state_from_db()

    def _load_state_from_db(self):
        """Load circuit breaker state from DB to Redis."""
        try:
            cb_state = self.db.query(CircuitBreakerState).filter(
                CircuitBreakerState.service_name == self.service_name
            ).first()

            if cb_state:
                # Sync DB state to Redis
                self.redis.hset(
                    self.redis_key,
                    mapping={
                        "state": cb_state.state,
                        "failure_count": cb_state.failure_count,
                        "last_failure_at": cb_state.last_failure_at.isoformat() if cb_state.last_failure_at else "",
                        "trip_count": cb_state.trip_count
                    }
                )
                logger.info(f"Loaded circuit breaker state from DB: {self.service_name} -> {cb_state.state}")
            else:
                # Initialize new circuit breaker
                self.redis.hset(
                    self.redis_key,
                    mapping={
                        "state": "CLOSED",
                        "failure_count": 0,
                        "last_failure_at": "",
                        "trip_count": 0
                    }
                )

        except Exception as e:
            logger.error(f"Failed to load circuit breaker state from DB: {e}")

    def record_success(self):
        """Record successful execution (reset failure count)."""
        try:
            # Update Redis
            self.redis.hset(self.redis_key, "failure_count", 0)
            self.redis.hset(self.redis_key, "state", "CLOSED")

            # Sync to DB
            self._sync_to_db()

            logger.debug(f"Circuit breaker success: {self.service_name}")

        except Exception as e:
            logger.error(f"Failed to record circuit breaker success: {e}")

    def record_failure(self):
        """Record failed execution (increment failure count, maybe trip breaker)."""
        try:
            # Increment failure count
            failure_count = self.redis.hincrby(self.redis_key, "failure_count", 1)
            self.redis.hset(self.redis_key, "last_failure_at", datetime.utcnow().isoformat())

            # Check if should trip
            if failure_count >= self.DEFAULT_FAILURE_THRESHOLD:
                self._trip_breaker()
            else:
                # Sync to DB
                self._sync_to_db()

            logger.warning(f"Circuit breaker failure: {self.service_name} ({failure_count}/{self.DEFAULT_FAILURE_THRESHOLD})")

        except Exception as e:
            logger.error(f"Failed to record circuit breaker failure: {e}")

    def _trip_breaker(self):
        """Trip circuit breaker to OPEN state."""
        try:
            # Update Redis
            self.redis.hset(self.redis_key, "state", "OPEN")
            trip_count = self.redis.hincrby(self.redis_key, "trip_count", 1)

            # Sync to DB
            self._sync_to_db()

            logger.critical(f"CIRCUIT BREAKER TRIPPED: {self.service_name} (trip_count={trip_count})")

            # TODO: Emit alert via NotificationService

        except Exception as e:
            logger.error(f"Failed to trip circuit breaker: {e}")

    def is_open(self) -> bool:
        """Check if circuit breaker is OPEN."""
        try:
            state = self.redis.hget(self.redis_key, "state")
            return state == b"OPEN" if state else False
        except Exception as e:
            logger.error(f"Failed to check circuit breaker state: {e}")
            return False  # Fail open (allow execution if Redis fails)

    def _sync_to_db(self):
        """Sync current Redis state to database."""
        try:
            state_data = self.redis.hgetall(self.redis_key)

            if not state_data:
                return

            # Parse Redis data
            state = state_data.get(b"state", b"CLOSED").decode("utf-8")
            failure_count = int(state_data.get(b"failure_count", b"0"))
            last_failure_str = state_data.get(b"last_failure_at", b"").decode("utf-8")
            trip_count = int(state_data.get(b"trip_count", b"0"))

            last_failure_at = None
            if last_failure_str:
                try:
                    last_failure_at = datetime.fromisoformat(last_failure_str)
                except:
                    pass

            # Upsert to DB
            cb_state = self.db.query(CircuitBreakerState).filter(
                CircuitBreakerState.service_name == self.service_name
            ).first()

            if cb_state:
                cb_state.state = state
                cb_state.failure_count = failure_count
                cb_state.last_failure_at = last_failure_at
                cb_state.trip_count = trip_count
                cb_state.updated_at = datetime.utcnow()
            else:
                cb_state = CircuitBreakerState(
                    service_name=self.service_name,
                    state=state,
                    failure_count=failure_count,
                    last_failure_at=last_failure_at,
                    trip_count=trip_count
                )
                self.db.add(cb_state)

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to sync circuit breaker state to DB: {e}")


@contextmanager
def distributed_lock(lock_key: str, timeout: int = DistributedLock.DEFAULT_TIMEOUT):
    """
    Context manager for distributed lock.

    Usage:
        with distributed_lock("lock:substitute:cluster-123"):
            # Critical section
            pass
    """
    redis = get_redis_client()
    lock = DistributedLock(redis, lock_key, timeout)

    try:
        if not lock.acquire():
            raise RuntimeError(f"Failed to acquire lock: {lock_key}")
        yield lock
    finally:
        lock.release()
