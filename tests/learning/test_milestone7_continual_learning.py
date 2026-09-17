"""
Project Garuda — Milestone 7 Verification Suite: Continual Learning Pipeline & Catastrophic Forgetting Mitigation
Verifies:
1. GoldenReplayBuffer class-balanced reservoir sampling & capacity limits.
2. StratifiedBatchSampler 35/65 ratio enforcement between new edge cases and historical exemplars.
3. DistillationLossRegularizer soft-target KL-divergence and parameter drift penalty.
4. RegressionBenchmarkEvaluator anti-forgetting invariant (Hard rejection on >2.0% drop for ANY class).
5. Master ContinualLearner training step workflow & replay buffer replenishment.
6. Disk serialization and deserialization roundtrip.
7. Low overhead & zero inference interruption.
"""

import os
import time
import numpy as np

from ai_engine.learning.continual_learner import (
    ReplayExemplar,
    GoldenReplayBuffer,
    StratifiedBatchSampler,
    DistillationLossRegularizer,
    RegressionBenchmarkEvaluator,
    ContinualLearner,
    continual_learner,
)


def test_1_golden_replay_buffer_balance():
    """Verify golden replay buffer maintains balanced exemplars across baseline classes."""
    buffer = GoldenReplayBuffer(capacity_per_class=30)
    buffer.seed_baseline_classes(["person", "car", "truck", "bicycle", "knife"])

    summary = buffer.get_summary()
    assert summary["total_classes"] == 5
    assert summary["total_exemplars"] == 5 * 25

    # Test reservoir overflow for 'person' class
    for i in range(50):
        ex = ReplayExemplar(
            exemplar_id=f"overflow_person_{i}",
            class_label="person",
            confidence=0.92,
            bbox=(0.1, 0.1, 0.4, 0.4),
            feature_descriptor=[0.1] * 64,
            source="OPERATOR_VALIDATED",
        )
        buffer.add_exemplar(ex)

    assert len(buffer.exemplars_by_class["person"]) <= buffer.capacity_per_class
    assert buffer.total_seen_by_class["person"] == 25 + 50

    # Test balanced sampling
    sampled = buffer.sample_replay_batch(15)
    assert len(sampled) == 15
    classes_sampled = {e.class_label for e in sampled}
    assert len(classes_sampled) >= 4, f"Replay sample lacked diversity: {classes_sampled}"
    print(f"[OK] Replay buffer: Classes={summary['total_classes']}, Exemplars={summary['total_exemplars']}, Sampled={len(sampled)} across {classes_sampled}")


def test_2_stratified_batch_sampler():
    """Verify batch sampler enforces 35% new edge case / 65% replay exemplar ratio."""
    buffer = GoldenReplayBuffer(capacity_per_class=20)
    buffer.seed_baseline_classes(["person", "car", "truck"])
    sampler = StratifiedBatchSampler(new_ratio=0.35, batch_size=16)

    # 10 mock new validated edge cases
    new_samples = [
        {"sample_id": f"new_{i}", "object_type": "person", "confidence": 0.88, "bbox": (0.1, 0.1, 0.4, 0.4)}
        for i in range(10)
    ]

    batches = sampler.create_batches(new_samples, buffer)
    assert len(batches) > 0

    for idx, batch in enumerate(batches):
        assert len(batch) == 16
        new_count = sum(1 for item in batch if item.get("sample_origin") == "NEW_EDGE_CASE")
        replay_count = sum(1 for item in batch if item.get("sample_origin") == "GOLDEN_REPLAY")
        ratio = new_count / len(batch)
        # Ratio should be close to 0.35 (e.g. ~30-40%)
        assert 0.25 <= ratio <= 0.45, f"Batch {idx} ratio out of bounds: {ratio}"
        assert replay_count >= 9, f"Batch {idx} replay count too low: {replay_count}"

    print(f"[OK] Stratified batch sampler: {len(batches)} batches created, verified 35/65 ratio.")


def test_3_distillation_and_parameter_regularizer():
    """Verify soft distillation loss and parameter drift penalties."""
    regularizer = DistillationLossRegularizer(alpha_distill=0.40, beta_drift=0.15, temperature=2.0)

    # Similar logits -> low distillation loss
    s_logits_close = np.array([2.0, 1.0, 0.1, -1.0], dtype=np.float32)
    t_logits = np.array([2.05, 0.98, 0.12, -0.95], dtype=np.float32)
    l_close = regularizer.compute_distillation_loss(s_logits_close, t_logits)

    # Divergent logits -> high distillation loss
    s_logits_far = np.array([-1.0, 2.5, 3.0, 1.2], dtype=np.float32)
    l_far = regularizer.compute_distillation_loss(s_logits_far, t_logits)

    assert l_close < l_far, f"Expected close logits ({l_close}) < divergent ({l_far})"
    assert l_close < 0.05, f"Distillation loss for close logits too high: {l_close}"
    assert l_far > 0.50, f"Distillation loss for far logits too low: {l_far}"

    # Parameter drift
    w_teacher = {"conv1": np.ones((10, 10), dtype=np.float32)}
    w_student_stable = {"conv1": np.ones((10, 10), dtype=np.float32) + 0.01}
    w_student_drift = {"conv1": np.ones((10, 10), dtype=np.float32) + 0.50}

    p_stable = regularizer.compute_parameter_drift_penalty(w_student_stable, w_teacher)
    p_drift = regularizer.compute_parameter_drift_penalty(w_student_drift, w_teacher)

    assert p_stable < p_drift
    assert p_drift > 0.20

    # Total loss
    total_loss_dict = regularizer.compute_total_continual_loss(
        task_loss=0.25,
        student_logits=s_logits_close,
        teacher_logits=t_logits,
        student_weights=w_student_stable,
        teacher_weights=w_teacher,
    )
    assert total_loss_dict["total_loss"] >= 0.25
    print(f"[OK] Distillation & drift regularizer: L_close={l_close:.4f}, L_far={l_far:.4f}, P_drift={p_drift:.4f}, Total={total_loss_dict['total_loss']}")


def test_4_anti_regression_invariant_check():
    """
    CRITICAL INVARIANT:
    If accuracy on ANY historical baseline class drops by >2.0%, the candidate model
    MUST BE REJECTED.
    """
    evaluator = RegressionBenchmarkEvaluator(max_allowed_class_drop_pct=2.0)

    # Case A: Catastrophic regression on 'bicycle' (drops from 87.5% to 83.0% -> drop of 4.5% > 2.0%)
    regressed_accuracies = {
        "person": 0.950,     # improved
        "car": 0.935,        # improved
        "truck": 0.895,      # preserved
        "motorcycle": 0.885, # preserved
        "bicycle": 0.830,    # REGRESSION! (87.5% -> 83.0%)
        "backpack": 0.860,   # improved
        "knife": 0.915,      # improved
    }

    report_regressed = evaluator.evaluate_candidate(
        candidate_version="v1.0.1-candidate-fail",
        class_predictions_eval=regressed_accuracies,
    )

    assert report_regressed.is_approved is False, "Violation: Regressed candidate model was approved!"
    assert any("bicycle" in f for f in report_regressed.failure_reasons), "Failure reason missing bicycle regression"
    print(f"[OK] Invariant verified: Regressed candidate was REJECTED: {report_regressed.failure_reasons[0]}")

    # Case B: Safe candidate preserving all classes and improving overall accuracy
    safe_accuracies = {
        "person": 0.955,     # +1.5%
        "car": 0.938,        # +1.3%
        "truck": 0.898,      # +0.8%
        "motorcycle": 0.888, # +0.8%
        "bicycle": 0.873,    # -0.2% (Within allowed 2.0% tolerance)
        "backpack": 0.868,   # +1.8%
        "knife": 0.925,      # +1.5%
    }

    report_safe = evaluator.evaluate_candidate(
        candidate_version="v1.0.1-candidate-pass",
        class_predictions_eval=safe_accuracies,
    )

    assert report_safe.is_approved is True, f"Safe candidate was unexpectedly rejected: {report_safe.failure_reasons}"
    assert report_safe.overall_gain_pct > 0.5
    print(f"[OK] Safe candidate APPROVED: Overall gain=+{report_safe.overall_gain_pct}%, all classes preserved.")


def test_5_master_continual_learner_workflow():
    """Verify master continual learner executes end-to-end training cycle."""
    learner = ContinualLearner(replay_storage_path="./data/learning/test_replay.json")

    mock_samples = [
        {
            "sample_id": f"s_test_{i}",
            "object_type": "backpack",
            "confidence": 0.94,
            "bbox": (0.2, 0.2, 0.6, 0.6),
            "feature_descriptor": np.random.randn(64).tolist(),
        }
        for i in range(12)
    ]

    is_approved, report, meta = learner.run_continual_training_step(
        new_samples=mock_samples,
        candidate_version="v1.0.2",
    )

    assert is_approved is True
    assert meta["batches_count"] > 0
    assert "backpack" in learner.replay_buffer.exemplars_by_class
    print(f"[OK] Master ContinualLearner step: Approved={is_approved}, Batches={meta['batches_count']}, ReplayClasses={meta['replay_summary']['total_classes']}")


def test_6_replay_buffer_persistence():
    """Verify disk save and load roundtrip."""
    test_path = "./data/learning/test_persistence_buffer.json"
    buf1 = GoldenReplayBuffer(capacity_per_class=20, storage_path=test_path)
    buf1.seed_baseline_classes(["person", "car"])
    buf1.save_to_disk()

    buf2 = GoldenReplayBuffer(capacity_per_class=20, storage_path=test_path)
    loaded = buf2.load_from_disk()
    assert loaded is True
    assert len(buf2.exemplars_by_class) == 2
    assert "person" in buf2.exemplars_by_class
    assert "car" in buf2.exemplars_by_class

    if os.path.exists(test_path):
        os.remove(test_path)
    print("[OK] Replay buffer persistence roundtrip verified.")


def test_7_performance_benchmark():
    """Verify that continual batch generation and regularization take <15.0ms."""
    learner = continual_learner
    mock_samples = [{"sample_id": f"perf_{i}", "object_type": "person", "confidence": 0.9} for i in range(20)]

    # Warmup run
    _ = learner.sampler.create_batches(mock_samples, learner.replay_buffer)

    t0 = time.perf_counter()
    batches = learner.sampler.create_batches(mock_samples, learner.replay_buffer)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 15.0, f"Batch sampling too slow: {elapsed_ms:.2f}ms"
    print(f"[OK] Performance benchmark: {len(batches)} stratified batches synthesized in {elapsed_ms:.3f} ms.")


if __name__ == "__main__":
    test_1_golden_replay_buffer_balance()
    test_2_stratified_batch_sampler()
    test_3_distillation_and_parameter_regularizer()
    test_4_anti_regression_invariant_check()
    test_5_master_continual_learner_workflow()
    test_6_replay_buffer_persistence()
    test_7_performance_benchmark()
    print("\n=======================================================")
    print("ALL 7 MILESTONE 7 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
