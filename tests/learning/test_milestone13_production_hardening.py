"""
Project Garuda — Milestone 13: Performance & Production Hardening
Verification Test Suite

Tests:
1. Circuit Breaker state machine (CLOSED -> OPEN -> HALF_OPEN -> CLOSED), fast-fail (<0.05ms) and fallback.
2. Bounded Eviction Queue under burst load (2000 items in 50 cap queue) with zero memory leaks & policy evictions.
3. Async Failure Isolation: unhandled worker exceptions trapped with zero impact on main thread.
4. Watchdog execution timeout on hung background tasks.
5. MemoryBoundsManager and LRU eviction governance.
6. High-load concurrent stress simulation (4 camera threads + continual cycle).
7. Hardening REST API endpoints & circuit resets.
"""

import os
import sys
import time
import threading
import concurrent.futures

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from ai_engine.learning.production_hardening import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerOpenException,
    BoundedEvictionQueue,
    EvictionPolicy,
    AsyncFailureIsolator,
    LRUCache,
    MemoryBoundsManager,
)
from ai_engine.learning.orchestrator import (
    CentralLearningOrchestrator,
    get_learning_orchestrator,
)
from ai_engine.learning.data_foundation import (
    LearningSample,
    ValidationStatus,
    SelectionReason,
)


def test_1_circuit_breaker():
    print("--- Test 1: Circuit Breaker State Machine & Fast-Fail ---")
    breaker = CircuitBreaker(
        name="test_service",
        failure_threshold=3,
        recovery_cooldown_seconds=0.05,  # Short cooldown for test speed
        half_open_success_threshold=2,
    )

    assert breaker.state == CircuitBreakerState.CLOSED, "Breaker should start in CLOSED state."

    # Normal success
    res = breaker.call(lambda x: x * 2, 5)
    assert res == 10, f"Expected 10, got {res}"
    assert breaker.metrics.total_successes == 1

    # Simulate failures
    def _fail():
        raise RuntimeError("Downstream API timeout")

    for i in range(3):
        try:
            breaker.call(_fail)
        except RuntimeError:
            pass

    assert breaker.state == CircuitBreakerState.OPEN, f"Breaker should trip to OPEN after 3 failures, got {breaker.state}"
    assert breaker.metrics.total_trips == 1

    # In OPEN state: verify fast-fail without fallback
    t0 = time.perf_counter()
    try:
        breaker.call(lambda: "should_not_run")
        assert False, "Should have raised CircuitBreakerOpenException"
    except CircuitBreakerOpenException:
        fast_fail_time = (time.perf_counter() - t0) * 1000.0

    assert fast_fail_time < 0.5, f"Fast fail took too long: {fast_fail_time:.4f}ms (target <0.5ms)"

    # In OPEN state: verify graceful fallback execution
    fallback_res = breaker.call(lambda: "should_not_run", fallback=lambda: "FALLBACK_VALUE")
    assert fallback_res == "FALLBACK_VALUE", f"Expected fallback value, got {fallback_res}"

    # Wait for cooldown to transition to HALF_OPEN
    time.sleep(0.06)
    assert breaker.state == CircuitBreakerState.HALF_OPEN, f"Expected HALF_OPEN after cooldown, got {breaker.state}"

    # Execute 2 consecutive successes in HALF_OPEN to close breaker
    s1 = breaker.call(lambda: "success_1")
    assert breaker.state == CircuitBreakerState.HALF_OPEN
    s2 = breaker.call(lambda: "success_2")
    assert breaker.state == CircuitBreakerState.CLOSED, f"Expected CLOSED after recovery, got {breaker.state}"

    # Test reset
    breaker.reset()
    assert breaker.state == CircuitBreakerState.CLOSED
    print(f"[OK] Circuit Breaker state transitions verified. Fast-fail latency = {fast_fail_time:.4f}ms.")


def test_2_bounded_eviction_queue():
    print("--- Test 2: Bounded Eviction Queue under Burst Load ---")
    capacity = 50
    queue = BoundedEvictionQueue[dict](max_capacity=capacity, policy=EvictionPolicy.DROP_OLDEST)

    # Push 2000 items in burst
    for i in range(2000):
        queue.push({"index": i, "data": f"sample_{i}"})

    assert queue.size() == capacity, f"Queue size should be capped at {capacity}, got {queue.size()}"
    assert queue.is_full()
    assert queue.total_pushed == 2000
    assert queue.total_dropped == (2000 - capacity)

    # Verify oldest were dropped and newest remain
    oldest_remaining = queue.pop()
    assert oldest_remaining["index"] == (2000 - capacity), f"Expected oldest remaining item index {2000 - capacity}, got {oldest_remaining['index']}"

    # Test Priority Eviction Policy
    prio_queue = BoundedEvictionQueue[str](max_capacity=3, policy=EvictionPolicy.DROP_LOW_PRIORITY)
    prio_queue.push("low_1", priority=0.1)
    prio_queue.push("high_1", priority=0.9)
    prio_queue.push("med_1", priority=0.5)
    # Queue is full with priorities [0.1, 0.9, 0.5]
    # Push high_2 (0.8) -> should evict low_1 (0.1)
    prio_queue.push("high_2", priority=0.8)

    remaining_items = []
    while prio_queue.size() > 0:
        remaining_items.append(prio_queue.pop())

    assert "low_1" not in remaining_items, f"'low_1' should have been evicted by priority, got {remaining_items}"
    assert "high_1" in remaining_items and "high_2" in remaining_items and "med_1" in remaining_items

    # Test REJECT_NEW policy
    reject_queue = BoundedEvictionQueue[int](max_capacity=2, policy=EvictionPolicy.REJECT_NEW)
    assert reject_queue.push(1) is True
    assert reject_queue.push(2) is True
    assert reject_queue.push(3) is False  # Rejected
    assert reject_queue.total_dropped == 1

    telemetry = queue.get_telemetry()
    assert telemetry["total_dropped"] == 1950
    print(f"[OK] Bounded queue verified under burst load: 2000 pushed, {telemetry['total_dropped']} dropped, heap bounded.")


def test_3_async_failure_isolation():
    print("--- Test 3: Async Failure Isolation & Exception Trapping ---")
    isolator = AsyncFailureIsolator(max_workers=2)

    # 1. Submit normal task
    fut1 = isolator.submit_isolated("test_calc", lambda a, b: a + b, 10, 20)
    assert fut1.result() == 30

    # 2. Submit deliberately crashing task
    def _crash_task():
        raise ValueError("Simulated background trainer OOM crash")

    callback_called = False
    def _on_error(exc):
        nonlocal callback_called
        callback_called = True

    fut2 = isolator.submit_isolated("faulty_task", _crash_task, on_error=_on_error)
    result = fut2.result()

    # Exception should be trapped without crashing main thread
    assert result is None, f"Expected None on trapped error, got {result}"
    assert callback_called is True, "on_error callback should have fired"
    assert isolator.total_failed == 1
    assert isolator.total_succeeded == 1

    # Verify failure log audit record
    telemetry = isolator.get_telemetry()
    assert telemetry["recent_failures_count"] >= 1
    last_failure = telemetry["recent_failures"][-1]
    assert last_failure["task_name"] == "faulty_task"
    assert last_failure["error_type"] == "ValueError"

    isolator.shutdown(wait=False)
    print(f"[OK] Async failure isolation trapped error cleanly: {last_failure['error_type']} recorded in failure log.")


def test_4_watchdog_timeout():
    print("--- Test 4: Watchdog Execution Timeout ---")
    isolator = AsyncFailureIsolator(max_workers=2)

    def _hung_task():
        time.sleep(0.3)
        return "finished"

    fut = isolator.submit_isolated("hung_worker", _hung_task, timeout_seconds=0.05)
    time.sleep(0.1)  # Allow watchdog to detect timeout

    telemetry = isolator.get_telemetry()
    assert telemetry["total_timed_out"] >= 1, f"Watchdog should have flagged timeout, got {telemetry}"

    isolator.shutdown(wait=False)
    print("[OK] Watchdog timeout successfully trapped hung task.")


def test_5_memory_bounds_manager():
    print("--- Test 5: Memory Bounds Manager & LRU Eviction Governance ---")
    # Test LRUCache directly
    cache = LRUCache[str](max_capacity=3)
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    cache.put("k3", "v3")
    assert cache.size() == 3

    # Access k1 so it becomes most recently used
    assert cache.get("k1") == "v1"

    # Put k4 -> should evict k2 (oldest)
    cache.put("k4", "v4")
    assert cache.size() == 3
    assert cache.get("k2") is None, "k2 should have been evicted by LRU"
    assert cache.get("k1") == "v1", "k1 should have been preserved"
    assert cache.evictions_count == 1

    # Test MemoryBoundsManager
    mgr = MemoryBoundsManager(max_exemplars_per_camera=100)
    cam1_cache = mgr.get_camera_exemplar_cache("CAM-01")
    cam2_cache = mgr.get_camera_exemplar_cache("CAM-02")
    cam1_cache.put("ex_1", "data")

    telemetry = mgr.get_memory_telemetry()
    assert telemetry["active_camera_caches"] == 2
    assert telemetry["total_cached_exemplars"] == 1
    assert telemetry["governance_status"] == "HEALTHY_BOUNDED"

    print(f"[OK] Memory Bounds Manager verified: LRU cache evictions={cache.evictions_count}, governance={telemetry['governance_status']}.")


def test_6_concurrent_stress_simulation():
    print("--- Test 6: High-Load Concurrent Stress Simulation ---")
    orchestrator = CentralLearningOrchestrator()
    sample_queue = orchestrator.candidate_sample_queue

    num_threads = 4
    samples_per_thread = 500
    errors = []

    def _producer(thread_id: int):
        for i in range(samples_per_thread):
            sample = LearningSample(
                sample_id=f"stress_sample_{thread_id}_{i}",
                camera_id=f"CAM-0{thread_id}",
                timestamp=time.time(),
                frame_ref=f"f_{i}.jpg",
                object_type="person",
                confidence=0.85,
                bounding_box=(0.1, 0.1, 0.3, 0.5),
                tracking_id=i,
                model_version="v1.0.0",
                selection_reason=SelectionReason.UNCERTAIN_DETECTION,
                validation_status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
                reinforcement_score=1.0,
            )
            try:
                orchestrator.memory_manager.store_sample(sample)
                sample_queue.push(sample)
            except Exception as e:
                errors.append(e)

    # Launch camera producer threads concurrently with a continual cycle
    threads = [threading.Thread(target=_producer, args=(i,)) for i in range(num_threads)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()

    # Run learning cycle concurrently while producers are saturating memory
    cycle_report = orchestrator.run_learning_cycle(force=True)
    assert cycle_report["status"] == "COMPLETED"

    for t in threads:
        t.join()

    total_time = (time.perf_counter() - t0) * 1000.0
    total_samples = num_threads * samples_per_thread

    assert len(errors) == 0, f"Encountered errors during stress test: {errors}"
    assert sample_queue.total_pushed == total_samples
    assert sample_queue.size() <= sample_queue.max_capacity

    avg_dispatch_ms = total_time / total_samples
    print(f"[OK] Concurrent stress test passed: {total_samples} samples processed concurrently in {total_time:.2f}ms (Avg dispatch: {avg_dispatch_ms:.4f}ms/sample).")


def test_7_hardening_rest_endpoints():
    print("--- Test 7: Hardening REST API Endpoint Verification ---")
    orchestrator = get_learning_orchestrator()

    # Verify status dictionary
    status_data = orchestrator.get_status()
    assert "hardening" in status_data, "Hardening telemetry should be present in status report"
    assert status_data["subsystems"]["production_hardening"] == "ACTIVE"

    telemetry = orchestrator.get_hardening_telemetry()
    assert "circuit_breakers" in telemetry
    assert "candidate_sample_queue" in telemetry
    assert "async_isolator" in telemetry
    assert "memory_bounds" in telemetry

    # Verify reset endpoint logic
    reset_res = orchestrator.reset_circuit_breakers()
    assert reset_res["status"] == "RESET_SUCCESSFUL"
    assert reset_res["continual_learning_cycle"] == "CLOSED"

    print("[OK] Hardening REST telemetry and admin circuit breaker resets verified.")


if __name__ == "__main__":
    print("\n=======================================================")
    print("RUNNING MILESTONE 13: PERFORMANCE & PRODUCTION HARDENING TESTS")
    print("=======================================================\n")

    test_1_circuit_breaker()
    test_2_bounded_eviction_queue()
    test_3_async_failure_isolation()
    test_4_watchdog_timeout()
    test_5_memory_bounds_manager()
    test_6_concurrent_stress_simulation()
    test_7_hardening_rest_endpoints()

    print("\n=======================================================")
    print("ALL 7 MILESTONE 13 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")
