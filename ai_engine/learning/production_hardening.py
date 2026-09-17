"""
Project Garuda — Adaptive & Continual Self-Learning Architecture
Milestone 13: Performance & Production Hardening

Provides mission-critical resilience, fault isolation, and backpressure controls:
1. CircuitBreaker: Fast-failing downstream or background dependencies during failures.
2. BoundedEvictionQueue: High-throughput bounded queue with policy-based drop (OOM prevention).
3. AsyncFailureIsolator: Thread pool isolation with watchdog timeouts and exception trapping.
4. MemoryBoundsManager: LRU cache bounding and memory footprint governance.
"""

from __future__ import annotations

import collections
import enum
import logging
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar

logger = logging.getLogger("garuda.learning.hardening")
T = TypeVar("T")


# =====================================================================
# 1. Circuit Breaker
# =====================================================================

class CircuitBreakerState(str, enum.Enum):
    CLOSED = "CLOSED"          # Normal operation, passes requests through
    OPEN = "OPEN"              # Tripped, immediately fast-fails or returns fallback
    HALF_OPEN = "HALF_OPEN"    # Probing health with limited test executions


class CircuitBreakerOpenException(Exception):
    """Raised when a protected call is attempted while the circuit breaker is OPEN."""
    pass


@dataclass
class CircuitBreakerMetrics:
    total_calls: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_trips: int = 0
    state_transitions: int = 0
    last_trip_timestamp: float = 0.0
    last_failure_reason: str = ""


class CircuitBreaker:
    """
    Production-grade circuit breaker to prevent cascading failures.
    Protects latency-sensitive video pipelines from slow or failing background services.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_cooldown_seconds: float = 5.0,
        half_open_success_threshold: int = 2,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_cooldown = recovery_cooldown_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_half_open_successes = 0
        self._last_state_change = time.time()
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

        self.metrics = CircuitBreakerMetrics()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            # Check for automatic transition from OPEN to HALF_OPEN after cooldown
            if self._state == CircuitBreakerState.OPEN:
                if (time.time() - self._last_failure_time) >= self.recovery_cooldown:
                    self._transition_to(CircuitBreakerState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        if self._state != new_state:
            logger.warning(
                f"[CircuitBreaker:{self.name}] Transition: {self._state.value} -> {new_state.value}"
            )
            self._state = new_state
            self._last_state_change = time.time()
            self.metrics.state_transitions += 1
            if new_state == CircuitBreakerState.OPEN:
                self.metrics.total_trips += 1
                self.metrics.last_trip_timestamp = time.time()
            elif new_state == CircuitBreakerState.HALF_OPEN:
                self._consecutive_half_open_successes = 0
            elif new_state == CircuitBreakerState.CLOSED:
                self._consecutive_failures = 0

    def call(
        self,
        func: Callable[..., T],
        *args: Any,
        fallback: Optional[Callable[..., T]] = None,
        **kwargs: Any,
    ) -> T:
        """
        Execute func protected by the circuit breaker.
        If OPEN, fast-fails or executes fallback immediately (<0.05ms).
        """
        current_state = self.state

        if current_state == CircuitBreakerState.OPEN:
            self.metrics.total_calls += 1
            if fallback is not None:
                return fallback(*args, **kwargs)
            raise CircuitBreakerOpenException(
                f"Circuit breaker '{self.name}' is OPEN. Fast-failing request."
            )

        # Attempt call in CLOSED or HALF_OPEN state
        self.metrics.total_calls += 1
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            if fallback is not None:
                return fallback(*args, **kwargs)
            raise

    def _on_success(self) -> None:
        with self._lock:
            self.metrics.total_successes += 1
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._consecutive_half_open_successes += 1
                if self._consecutive_half_open_successes >= self.half_open_success_threshold:
                    self._transition_to(CircuitBreakerState.CLOSED)
            elif self._state == CircuitBreakerState.CLOSED:
                self._consecutive_failures = 0

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self.metrics.total_failures += 1
            self.metrics.last_failure_reason = str(exc)
            self._last_failure_time = time.time()

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately trips back to OPEN
                self._transition_to(CircuitBreakerState.OPEN)
            elif self._state == CircuitBreakerState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    self._transition_to(CircuitBreakerState.OPEN)

    def reset(self) -> None:
        """Administratively reset the breaker to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitBreakerState.CLOSED)
            self._consecutive_failures = 0
            self._consecutive_half_open_successes = 0

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_threshold": self.failure_threshold,
            "recovery_cooldown_seconds": self.recovery_cooldown,
            "metrics": {
                "total_calls": self.metrics.total_calls,
                "total_successes": self.metrics.total_successes,
                "total_failures": self.metrics.total_failures,
                "total_trips": self.metrics.total_trips,
                "state_transitions": self.metrics.state_transitions,
                "last_trip_timestamp": self.metrics.last_trip_timestamp,
                "last_failure_reason": self.metrics.last_failure_reason,
            },
        }


# =====================================================================
# 2. Bounded Eviction Queue (Burst & OOM Protection)
# =====================================================================

class EvictionPolicy(str, enum.Enum):
    DROP_OLDEST = "DROP_OLDEST"            # Discards oldest item in FIFO order
    DROP_LOW_PRIORITY = "DROP_LOW_PRIORITY" # Discards item with lowest priority score
    REJECT_NEW = "REJECT_NEW"              # Rejects the incoming item, leaves queue intact


@dataclass
class QueueItem(Generic[T]):
    data: T
    priority: float
    timestamp: float = field(default_factory=time.time)


class BoundedEvictionQueue(Generic[T]):
    """
    Thread-safe bounded queue with automatic eviction policies.
    Guarantees that high-frequency candidate sample mining during crowd surges
    never causes Out-Of-Memory (OOM) fatal leaks.
    """

    def __init__(
        self,
        max_capacity: int = 1000,
        policy: EvictionPolicy = EvictionPolicy.DROP_OLDEST,
    ) -> None:
        self.max_capacity = max(1, max_capacity)
        self.policy = policy
        self._deque: collections.deque[QueueItem[T]] = collections.deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

        # Telemetry counters
        self.total_pushed: int = 0
        self.total_popped: int = 0
        self.total_dropped: int = 0
        self.peak_size: int = 0

    def push(self, item: T, priority: float = 0.0) -> bool:
        """
        Push an item into the queue.
        If full, applies the eviction policy.
        Returns True if item was enqueued, False if rejected.
        """
        with self._lock:
            self.total_pushed += 1
            new_item = QueueItem(data=item, priority=priority)

            if len(self._deque) >= self.max_capacity:
                if self.policy == EvictionPolicy.REJECT_NEW:
                    self.total_dropped += 1
                    return False
                elif self.policy == EvictionPolicy.DROP_OLDEST:
                    self._deque.popleft()
                    self.total_dropped += 1
                elif self.policy == EvictionPolicy.DROP_LOW_PRIORITY:
                    # Find and remove lowest priority item
                    min_idx = 0
                    min_prio = self._deque[0].priority
                    for idx, q_item in enumerate(self._deque):
                        if q_item.priority < min_prio:
                            min_prio = q_item.priority
                            min_idx = idx

                    # If the new item has lower priority than all existing items, drop the new item
                    if priority < min_prio:
                        self.total_dropped += 1
                        return False

                    # Otherwise remove the lowest priority existing item
                    del self._deque[min_idx]
                    self.total_dropped += 1

            self._deque.append(new_item)
            current_len = len(self._deque)
            if current_len > self.peak_size:
                self.peak_size = current_len

            self._not_empty.notify()
            return True

    def pop(self, block: bool = False, timeout: Optional[float] = None) -> Optional[T]:
        """
        Pop the next item from the queue.
        If block=True, waits up to timeout seconds for an item.
        Returns the data or None if empty.
        """
        with self._not_empty:
            if not self._deque:
                if not block:
                    return None
                if not self._not_empty.wait(timeout=timeout):
                    return None
                if not self._deque:
                    return None

            item = self._deque.popleft()
            self.total_popped += 1
            return item.data

    def size(self) -> int:
        with self._lock:
            return len(self._deque)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._deque) >= self.max_capacity

    def clear(self) -> None:
        with self._lock:
            self._deque.clear()

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "current_size": len(self._deque),
                "max_capacity": self.max_capacity,
                "utilization_pct": round((len(self._deque) / self.max_capacity) * 100, 2),
                "policy": self.policy.value,
                "total_pushed": self.total_pushed,
                "total_popped": self.total_popped,
                "total_dropped": self.total_dropped,
                "peak_size": self.peak_size,
            }


# =====================================================================
# 3. Asynchronous Failure Isolator & Worker Scheduler
# =====================================================================

@dataclass
class FailureLogEntry:
    task_name: str
    error_type: str
    error_message: str
    timestamp: float = field(default_factory=time.time)


class AsyncFailureIsolator:
    """
    Dedicated worker thread pool for background continual learning tasks.
    Enforces complete exception trapping and watchdog execution deadlines.
    Guarantees that a training failure or compute timeout NEVER crashes the camera thread.
    """

    def __init__(self, max_workers: int = 2, max_log_entries: int = 100) -> None:
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="garuda-learning-worker",
        )
        self.failure_log: collections.deque[FailureLogEntry] = collections.deque(
            maxlen=max_log_entries
        )
        self._lock = threading.Lock()

        # Telemetry
        self.total_submitted: int = 0
        self.total_succeeded: int = 0
        self.total_failed: int = 0
        self.total_timed_out: int = 0

    def submit_isolated(
        self,
        task_name: str,
        func: Callable[..., T],
        *args: Any,
        timeout_seconds: Optional[float] = None,
        on_success: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        **kwargs: Any,
    ) -> Future[Optional[T]]:
        """
        Execute func on an isolated worker thread.
        Any exception is trapped and recorded in failure_log.
        """
        with self._lock:
            self.total_submitted += 1

        def _worker_wrapper() -> Optional[T]:
            try:
                result = func(*args, **kwargs)
                with self._lock:
                    self.total_succeeded += 1
                if on_success:
                    try:
                        on_success(result)
                    except Exception as cb_exc:
                        logger.error(f"Error in on_success callback for '{task_name}': {cb_exc}")
                return result
            except Exception as exc:
                with self._lock:
                    self.total_failed += 1
                    self.failure_log.append(
                        FailureLogEntry(
                            task_name=task_name,
                            error_type=type(exc).__name__,
                            error_message=str(exc),
                        )
                    )
                logger.error(f"[AsyncFailureIsolator] Task '{task_name}' failed: {exc}", exc_info=True)
                if on_error:
                    try:
                        on_error(exc)
                    except Exception as cb_exc:
                        logger.error(f"Error in on_error callback for '{task_name}': {cb_exc}")
                return None

        future = self._executor.submit(_worker_wrapper)

        if timeout_seconds is not None:
            # Watchdog thread to monitor execution timeout
            def _watchdog() -> None:
                try:
                    future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    with self._lock:
                        self.total_timed_out += 1
                        self.failure_log.append(
                            FailureLogEntry(
                                task_name=task_name,
                                error_type="WatchdogTimeoutError",
                                error_message=f"Task exceeded execution timeout of {timeout_seconds}s",
                            )
                        )
                    logger.warning(
                        f"[AsyncFailureIsolator] Task '{task_name}' timed out after {timeout_seconds}s"
                    )

            threading.Thread(target=_watchdog, daemon=True, name=f"watchdog-{task_name}").start()

        return future

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "max_workers": self.max_workers,
                "total_submitted": self.total_submitted,
                "total_succeeded": self.total_succeeded,
                "total_failed": self.total_failed,
                "total_timed_out": self.total_timed_out,
                "recent_failures_count": len(self.failure_log),
                "recent_failures": [
                    {
                        "task_name": f.task_name,
                        "error_type": f.error_type,
                        "error_message": f.error_message,
                        "timestamp": f.timestamp,
                    }
                    for f in list(self.failure_log)[-5:]
                ],
            }


# =====================================================================
# 4. Memory Bounds Manager (LRU Cache Bounds)
# =====================================================================

class LRUCache(Generic[T]):
    """Thread-safe Least-Recently-Used (LRU) cache with bounded capacity."""

    def __init__(self, max_capacity: int = 500) -> None:
        self.max_capacity = max(1, max_capacity)
        self._data: collections.OrderedDict[str, T] = collections.OrderedDict()
        self._lock = threading.Lock()
        self.evictions_count: int = 0

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: T) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = value
            if len(self._data) > self.max_capacity:
                self._data.popitem(last=False)
                self.evictions_count += 1

    def remove(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())


class MemoryBoundsManager:
    """
    Central memory bounds manager enforcing strict entry limits and LRU eviction
    across all in-memory learning submodules to prevent long-running heap inflation.
    """

    def __init__(
        self,
        max_exemplars_per_camera: int = 500,
        max_cached_lineage_nodes: int = 200,
        max_cached_federated_payloads: int = 1000,
    ) -> None:
        self.max_exemplars = max_exemplars_per_camera
        self.max_lineage_nodes = max_cached_lineage_nodes
        self.max_federated_payloads = max_cached_federated_payloads

        # Subsystem LRU caches
        self.exemplar_caches: Dict[str, LRUCache[Any]] = {}
        self.lineage_cache: LRUCache[Any] = LRUCache(max_capacity=max_cached_lineage_nodes)
        self.federated_payload_cache: LRUCache[Any] = LRUCache(
            max_capacity=max_cached_federated_payloads
        )
        self._lock = threading.Lock()

    def get_camera_exemplar_cache(self, camera_id: str) -> LRUCache[Any]:
        with self._lock:
            if camera_id not in self.exemplar_caches:
                self.exemplar_caches[camera_id] = LRUCache(max_capacity=self.max_exemplars)
            return self.exemplar_caches[camera_id]

    def prune_stale_caches(self) -> int:
        """Prunes any empty or idle camera caches."""
        with self._lock:
            pruned = 0
            to_remove = [cid for cid, c in self.exemplar_caches.items() if c.size() == 0]
            for cid in to_remove:
                del self.exemplar_caches[cid]
                pruned += 1
            return pruned

    def get_memory_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            total_exemplars = sum(c.size() for c in self.exemplar_caches.values())
            total_exemplar_evictions = sum(c.evictions_count for c in self.exemplar_caches.values())
            return {
                "active_camera_caches": len(self.exemplar_caches),
                "total_cached_exemplars": total_exemplars,
                "total_exemplar_evictions": total_exemplar_evictions,
                "cached_lineage_nodes": self.lineage_cache.size(),
                "lineage_evictions": self.lineage_cache.evictions_count,
                "cached_federated_payloads": self.federated_payload_cache.size(),
                "federated_evictions": self.federated_payload_cache.evictions_count,
                "governance_status": "HEALTHY_BOUNDED",
            }
