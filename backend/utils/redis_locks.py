"""
Redis distributed locks — shared by all engines.

Usage:
    from backend.utils.redis_locks import cluster_mutex, workload_lock

    with cluster_mutex(redis, cluster_id, owner="placement_controller") as acquired:
        if not acquired:
            return
        _process_cluster(cluster_id)
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

CLUSTER_MUTEX_KEY = "spot:cluster_mutex:{cluster_id}"
WORKLOAD_LOCK_KEY = "lock:workload:{cluster_id}:{workload_id}"


class HeartbeatLock:
    """
    Redis distributed lock with automatic TTL renewal.

    A daemon thread renews the lock every ``ttl // 3`` seconds so that
    long-running critical sections (e.g. a full PlacementController cycle)
    never expire due to wall-clock TTL while still holding the mutex.

    On release the renewal thread is stopped and the key deleted iff this
    instance still owns it (owner token comparison prevents accidental
    deletion of a lock re-acquired by another engine after an edge-case
    expiry).
    """

    def __init__(self, redis_client, key: str, owner: str, ttl: int = 60):
        self.redis = redis_client
        self.key = key
        self.owner = owner
        self.ttl = ttl
        self._renew_interval = max(1, ttl // 3)
        self._acquired = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def acquire(self) -> bool:
        self._acquired = bool(self.redis.set(self.key, self.owner, nx=True, ex=self.ttl))
        if self._acquired:
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._renew_loop, daemon=True, name=f"heartbeat-{self.key}")
            self._thread.start()
        return self._acquired

    def _renew_loop(self) -> None:
        while not self._stop_event.wait(self._renew_interval):
            try:
                raw = self.redis.get(self.key)
                current = raw.decode() if isinstance(raw, bytes) else raw
                if current == self.owner:
                    self.redis.expire(self.key, self.ttl)
                else:
                    break
            except Exception:
                pass

    def release(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._acquired:
            try:
                raw = self.redis.get(self.key)
                current = raw.decode() if isinstance(raw, bytes) else raw
                if current == self.owner:
                    self.redis.delete(self.key)
            except Exception:
                pass


@contextmanager
def cluster_mutex(redis_client, cluster_id: str, owner: str, ttl: int = 60):
    """
    Per-cluster Redis mutex shared by placement_controller and auto_rebalancer.

    Backed by HeartbeatLock — the TTL is renewed every ``ttl // 3`` seconds
    by a daemon thread, so a cycle that takes longer than the initial TTL
    does not silently expire the lock and allow concurrent engine entry.

    Yields True if the mutex was acquired (caller should proceed).
    Yields False if another engine holds the mutex (caller should skip).

    Key: spot:cluster_mutex:{cluster_id}
    TTL: configurable, default 60s (renewed automatically).
    """
    lock = HeartbeatLock(
        redis_client,
        CLUSTER_MUTEX_KEY.format(cluster_id=cluster_id),
        owner,
        ttl,
    )
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        lock.release()


@contextmanager
def workload_lock(redis_client, cluster_id: str, workload_id: str, owner: str, ttl: int = 30):
    """
    Per-workload Redis lock preventing parallel actions on the same workload.

    Yields True if the lock was acquired.
    Yields False if another cycle holds the lock (caller should skip).

    Key: lock:workload:{cluster_id}:{workload_id}
    TTL: configurable, default 30s.
    """
    key = WORKLOAD_LOCK_KEY.format(cluster_id=cluster_id, workload_id=workload_id)
    acquired = redis_client.set(key, owner, nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            redis_client.delete(key)
