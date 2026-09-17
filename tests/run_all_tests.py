"""
Project Garuda — Master Test Suite Runner
Orchestrates and executes all unit, integration, and milestone regression tests.

Usage:
  python tests/run_all_tests.py                  # Runs all tests
  python tests/run_all_tests.py --learning       # Runs learning milestones 1-14
  python tests/run_all_tests.py --vision         # Runs vision/pipeline tests
  python tests/run_all_tests.py --milestone 14   # Runs specific milestone test
"""

import argparse
import os
import subprocess
import sys
import time

# Determine project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
LEARNING_DIR = os.path.join(SCRIPT_DIR, "learning")
VISION_DIR = os.path.join(SCRIPT_DIR, "vision")

LEARNING_TESTS = [
    ("Milestone 1: Foundation", os.path.join(LEARNING_DIR, "test_milestone1_foundation.py")),
    ("Milestone 2: Active Learning", os.path.join(LEARNING_DIR, "test_milestone2_active_learning.py")),
    ("Milestone 3: Human RLHF Validation", os.path.join(LEARNING_DIR, "test_milestone3_human_validation.py")),
    ("Milestone 4: Camera Profile Adaptation", os.path.join(LEARNING_DIR, "test_milestone4_camera_adaptation.py")),
    ("Milestone 5: Self-Supervised Learning", os.path.join(LEARNING_DIR, "test_milestone5_self_supervised.py")),
    ("Milestone 6: Anomaly & Novelty", os.path.join(LEARNING_DIR, "test_milestone6_anomaly_novelty.py")),
    ("Milestone 7: Continual Learning Pipeline", os.path.join(LEARNING_DIR, "test_milestone7_continual_learning.py")),
    ("Milestone 8: Synthetic Augmentation", os.path.join(LEARNING_DIR, "test_milestone8_synthetic_augmentation.py")),
    ("Milestone 9: Safe Shadow Deployment", os.path.join(LEARNING_DIR, "test_milestone9_shadow_deployment.py")),
    ("Milestone 10: Federated Representation Sharing", os.path.join(LEARNING_DIR, "test_milestone10_federated_sharing.py")),
    ("Milestone 11: Orchestrator & Lineage", os.path.join(LEARNING_DIR, "test_milestone11_orchestrator_lineage.py")),
    ("Milestone 12: Dashboard Observability", os.path.join(LEARNING_DIR, "test_milestone12_dashboard_observability.py")),
    ("Milestone 13: Production Hardening", os.path.join(LEARNING_DIR, "test_milestone13_production_hardening.py")),
    ("Milestone 14: Full E2E System Validation", os.path.join(LEARNING_DIR, "test_milestone14_e2e_system_validation.py")),
    ("Active Learning Unit Suite", os.path.join(LEARNING_DIR, "test_active_learning.py")),
]

VISION_TESTS = [
    ("ANPR OCR Pipeline", os.path.join(VISION_DIR, "test_anpr_pipeline.py")),
    ("Homography & Night Vision", os.path.join(VISION_DIR, "test_homography_and_night_vision.py")),
    ("Snapshot & Evidence Anchoring", os.path.join(VISION_DIR, "test_snapshot_evidence.py")),
    ("Thermal Radiometric Vision", os.path.join(VISION_DIR, "test_thermal_vision.py")),
    ("Weapon Threat Detector Pipeline", os.path.join(VISION_DIR, "test_weapon_pipeline.py")),
    ("Five-Pillar Architecture Integration", os.path.join(VISION_DIR, "test_five_pillars_integration.py")),
]


def run_test_suite(tests_to_run: list[tuple[str, str]]) -> bool:
    print("\n" + "=" * 70)
    print(f"PROJECT GARUDA — EXECUTING {len(tests_to_run)} TEST SUITES")
    print("=" * 70 + "\n")

    passed_count = 0
    failed_count = 0
    results = []

    # Configure environment with project root and backend
    env = os.environ.copy()
    backend_dir = os.path.join(PROJECT_ROOT, "backend")
    env["PYTHONPATH"] = PROJECT_ROOT + os.pathsep + backend_dir + os.pathsep + env.get("PYTHONPATH", "")

    total_start = time.time()

    for name, filepath in tests_to_run:
        if not os.path.exists(filepath):
            print(f"[SKIP] {name}: File not found ({filepath})")
            continue

        print(f"Running: {name} ...", end=" ", flush=True)
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, filepath],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        duration = time.time() - t0

        if proc.returncode == 0:
            print(f"PASSED ({duration:.2f}s)")
            passed_count += 1
            results.append((name, "PASSED", duration, ""))
        else:
            print(f"FAILED ({duration:.2f}s)")
            failed_count += 1
            error_output = proc.stdout + "\n" + proc.stderr
            results.append((name, "FAILED", duration, error_output.strip()))

    total_duration = time.time() - total_start

    print("\n" + "=" * 70)
    print("TEST EXECUTION SUMMARY")
    print("=" * 70)
    for name, status, duration, _ in results:
        status_str = "[OK]  PASSED" if status == "PASSED" else "[ERR] FAILED"
        print(f"  {status_str:14} | {duration:6.2f}s | {name}")
    print("-" * 70)
    print(f"Total: {passed_count + failed_count} | Passed: {passed_count} | Failed: {failed_count} | Time: {total_duration:.2f}s")
    print("=" * 70 + "\n")

    if failed_count > 0:
        print("\n--- FAILURE DETAILS ---")
        for name, status, _, err in results:
            if status == "FAILED":
                print(f"\n>>> {name} Output:\n{err}\n" + "-" * 50)
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Project Garuda Master Test Suite Runner")
    parser.add_argument("--learning", "-l", action="store_true", help="Run only Adaptive Learning milestone tests (M1-M14)")
    parser.add_argument("--vision", "-v", action="store_true", help="Run only Vision / Pipeline tests")
    parser.add_argument("--milestone", "-m", type=int, help="Run a specific milestone (1-14)")

    args = parser.parse_args()

    if args.milestone:
        target_name = f"Milestone {args.milestone}:"
        selected = [t for t in LEARNING_TESTS if target_name in t[0]]
        if not selected:
            print(f"Error: Milestone {args.milestone} not found. Available milestones: 1-14.")
            sys.exit(1)
        success = run_test_suite(selected)
    elif args.learning:
        success = run_test_suite(LEARNING_TESTS)
    elif args.vision:
        success = run_test_suite(VISION_TESTS)
    else:
        # Default: run all tests
        all_tests = LEARNING_TESTS + VISION_TESTS
        success = run_test_suite(all_tests)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
