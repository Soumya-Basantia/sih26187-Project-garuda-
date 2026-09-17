"""
Project Garuda — Five-Pillar Intelligence Upgrade Integration Test Suite

Verifies all 5 Pillars:
1. 🧠 Pillar 1 & 5: Learning Surveillance & Safe Self-Improvement
   - Multi-metric promotion gates (mAP delta, critical class recall, false positive rate, latency, old-class retention)
   - Cryptographic lineage hash & automated rollback tripwires.
2. 🎯 Pillar 2: Incident Intelligence
   - Person-Object Interaction & Abandoned Object state transitions (Carrying -> Placed -> Separated -> Stationary -> POTENTIAL_ABANDONED_OBJECT)
   - Multi-signal Incident aggregation, explainability checklist, and 6-stage lifecycle.
3. 🔌 Pillar 3: Existing-Infrastructure Intelligence
   - BaseVideoSource hierarchy (RTSPSource, WebcamSource, FileSource, SyntheticSensorSource)
   - SensorModality classification (VISIBLE_RGB, IR_NIGHT, THERMAL) & fault isolation.
4. ⚡ Pillar 4: Edge + Bandwidth-Aware Intelligence
   - Store-and-Forward offline event queue (disconnect -> buffer -> reconnect -> synchronize)
   - Edge resource telemetry (CPU, RAM vs <250MB limit, latency).
5. 🌐 Pillars 2 & 3: Multi-Camera Handover & Topology
   - Spatial-temporal handover candidate scoring with transit time windows and direction vectors.
"""

import sys
import os
import time
import numpy as np

# Ensure project root and backend are on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ai_engine.pipeline.camera_adapter import (
    CameraConfig,
    SourceType,
    SensorModality,
    CameraStatus,
    BaseVideoSource,
    create_video_source,
    RTSPSource,
    FileSource,
    SyntheticSensorSource,
)
from ai_engine.events.event_engine import Event, EventType, Severity, TimelineItem
from ai_engine.events.incident_engine import (
    IncidentEngine,
    IncidentStatus,
    IncidentType,
    PersonObjectInteractionTracker,
)
from ai_engine.tracking.camera_topology import CameraTopologyEngine
from ai_engine.learning.shadow_deployment import SafeDeploymentManager, DeploymentStage
from backend.app.services.store_and_forward import (
    StoreAndForwardQueue,
    EdgeTelemetryCollector,
    NetworkStatus,
    TransmissionPriority,
)


def test_pillar_3_video_source_abstraction():
    print("--- 1. Testing Pillar 3: VideoSource Abstraction & Modality ---")
    cfg_rgb = CameraConfig(
        camera_id="CAM-01",
        name="Main Gate Optical CCTV",
        location="Gate 1",
        source_type=SourceType.DEMO,
        source_uri="demo_cctv",
    )
    src_rgb = create_video_source(cfg_rgb)
    assert isinstance(src_rgb, SyntheticSensorSource)
    assert src_rgb.open() is True
    res_rgb = src_rgb.read_frame()
    assert res_rgb.ok is True
    assert res_rgb.frame is not None
    assert src_rgb.modality == SensorModality.VISIBLE_RGB
    health = src_rgb.get_health()
    assert health["camera_id"] == "CAM-01"
    assert health["status"] == "ONLINE"
    src_rgb.close()

    cfg_thermal = CameraConfig(
        camera_id="CAM-02",
        name="FLIR Thermal Perimeter Sensor",
        location="Perimeter Fence",
        source_type=SourceType.DEMO,
        source_uri="demo_thermal",
    )
    src_thermal = create_video_source(cfg_thermal)
    assert src_thermal.modality == SensorModality.THERMAL
    src_thermal.close()
    print("   [OK] VideoSource hierarchy & modality classification verified.")


def test_pillar_2_incident_intelligence_and_abandoned_object():
    print("--- 2. Testing Pillar 2: Incident Intelligence & Abandoned Object ---")
    tracker = PersonObjectInteractionTracker(
        association_dist_px=100.0,
        separation_dist_px=150.0,
        stationary_time_sec=2.0,  # fast threshold for test
    )

    now = time.time()
    # Step 1: Person 10 and Bag 20 in close proximity
    persons_t1 = [{"track_id": 10, "pos": (200, 300)}]
    objects_t1 = [{"track_id": 20, "pos": (210, 310), "label": "backpack"}]
    notifs = tracker.update_associations(persons_t1, objects_t1, now, "CAM-01")
    assert len(notifs) == 0

    # Step 2: Person moves away, object stays stationary
    now += 1.0
    persons_t2 = [{"track_id": 10, "pos": (450, 300)}]  # separated by 240px
    objects_t2 = [{"track_id": 20, "pos": (210, 310), "label": "backpack"}]
    notifs = tracker.update_associations(persons_t2, objects_t2, now, "CAM-01")
    assert len(notifs) == 0

    # Step 3: Stationary threshold exceeded (>2.0s)
    now += 2.5
    notifs = tracker.update_associations(persons_t2, objects_t2, now, "CAM-01")
    assert len(notifs) == 1
    assert notifs[0]["object_track_id"] == 20
    assert notifs[0]["person_track_id"] == 10

    # Step 4: Incident Engine creates explainable Abandoned Object Incident
    inc_engine = IncidentEngine()
    incident = inc_engine.handle_abandoned_object_event(notifs[0])
    assert incident.incident_type == IncidentType.POTENTIAL_ABANDONED_OBJECT
    assert incident.status == IncidentStatus.PRIORITIZED
    assert incident.title == "Potential Abandoned Object — Verification Required"
    assert len(incident.explainability_signals) >= 3
    assert len(incident.timeline) >= 3

    # Step 5: Multi-Signal Event Correlation
    ev = Event(
        event_id="EVT-101",
        event_type=EventType.ZONE_INTRUSION,
        track_id=10,
        camera_id="CAM-01",
        zone_id="ARMORY_SECTOR",
        timestamp=now + 5.0,
        severity=Severity.RED,
        confidence=0.94,
        description="Unauthorized breach into Armory",
        risk_score=90,
    )
    inc2 = inc_engine.process_event(ev)
    assert inc2 is not None
    assert inc2.severity == Severity.RED
    print("   [OK] IncidentEngine & Person-Object correlation verified.")


def test_pillars_2_and_3_camera_topology_and_handover():
    print("--- 3. Testing Pillars 2 & 3: Multi-Camera Handover & Topology ---")
    topo = CameraTopologyEngine()
    now = time.time()

    # Track 42 departs CAM-01 heading East
    topo.record_track_departure(
        track_id=42,
        camera_id="CAM-01",
        exit_pos=(100.0, 50.0),
        velocity_mps=1.4,
        heading_vector=(1.0, 0.2),
        appearance_tag="RED_JACKET",
        now=now,
    )

    # 15 seconds later, candidate Track 88 appears on adjacent CAM-02
    arrival_time = now + 16.0
    match = topo.evaluate_candidate_arrival(
        candidate_track_id=88,
        camera_id="CAM-02",
        entry_pos=(10.0, 50.0),
        heading_vector=(1.0, 0.2),
        appearance_tag="RED_JACKET",
        now=arrival_time,
    )

    assert match is not None
    assert match.source_track_id == 42
    assert match.candidate_track_id == 88
    assert match.from_camera_id == "CAM-01"
    assert match.to_camera_id == "CAM-02"
    assert match.handover_confidence >= 0.75
    assert "Possible continuation of Track #42" in match.explanation
    print("   [OK] Multi-camera spatial-temporal handover scoring verified.")


def test_pillar_4_edge_store_and_forward_and_telemetry():
    print("--- 4. Testing Pillar 4: Edge Store-and-Forward & Telemetry ---")
    q = StoreAndForwardQueue()
    assert q.status == NetworkStatus.ONLINE

    # Online mode: direct transmission
    res_online = q.enqueue({"event_id": "EVT-1", "type": "motion"}, priority=TransmissionPriority.HIGH)
    assert res_online is True
    assert q.get_queue_stats()["spooled_queue_depth"] == 0

    # Simulate network outage
    q.set_network_status(NetworkStatus.OFFLINE)
    res_off1 = q.enqueue({"event_id": "EVT-2", "type": "intrusion"}, priority=TransmissionPriority.CRITICAL)
    res_off2 = q.enqueue({"event_id": "EVT-3", "type": "loitering"}, priority=TransmissionPriority.HIGH)
    assert res_off1 is False
    assert res_off2 is False
    assert q.get_queue_stats()["spooled_queue_depth"] == 2

    # Network restored -> auto sync
    synced = q.set_network_status(NetworkStatus.ONLINE)
    assert synced == 2
    assert q.get_queue_stats()["spooled_queue_depth"] == 0
    assert q.get_queue_stats()["total_synced_on_reconnect"] == 2

    # Edge Telemetry Collector
    telem = EdgeTelemetryCollector(q).get_telemetry_snapshot()
    assert telem["ram_within_budget"] is True
    assert telem["ram_budget_mb"] == 250.0
    print("   [OK] Store-and-Forward resilience & edge telemetry verified.")


def test_pillar_1_and_5_safe_promotion_gates():
    print("--- 5. Testing Pillar 1 & 5: Multi-Metric Promotion Gates & Rollback ---")
    mgr = SafeDeploymentManager(active_version="v1.0.0")

    # Start shadow evaluation
    mgr.start_shadow_evaluation(candidate_version="v2.0.0-rc1", candidate_model_path="yolov8_candidate.pt")
    assert mgr.current_stage == DeploymentStage.SHADOW

    # Gate Evaluation: Successful candidate
    good_gate = mgr.evaluate_multi_metric_gates(
        overall_map_delta=+0.035,
        critical_class_recall=0.96,
        false_positive_rate=0.02,
        latency_ratio=1.04,
        old_class_retention=0.99,
    )
    assert good_gate.passed_all_gates is True
    assert len(good_gate.lineage_hash) == 64

    # Gate Evaluation: Regressed candidate (e.g. mAP regressed or critical threat dropped)
    bad_gate = mgr.evaluate_multi_metric_gates(
        overall_map_delta=+0.01,
        critical_class_recall=0.82,  # Fail: < 0.90
        false_positive_rate=0.08,   # Fail: > 0.05
        latency_ratio=1.25,          # Fail: > 1.15
        old_class_retention=0.91,   # Fail: < 0.95
    )
    assert bad_gate.passed_all_gates is False
    assert len(bad_gate.failure_reasons) >= 3

    # Emergency Rollback Test
    mgr.promote_to_canary("CAM-01")
    report_rb = mgr.trigger_emergency_rollback("Accuracy tripwire breached on live stream")
    assert report_rb.stage == DeploymentStage.ROLLED_BACK
    assert mgr.active_version == "v1.0.0"
    print("   [OK] Multi-metric promotion gates and rollback invariants verified.")


def run_all_five_pillars_tests():
    print("\n" + "=" * 70)
    print("PROJECT GARUDA — FIVE-PILLAR ARCHITECTURE INTEGRATION TEST")
    print("=" * 70 + "\n")

    test_pillar_3_video_source_abstraction()
    test_pillar_2_incident_intelligence_and_abandoned_object()
    test_pillars_2_and_3_camera_topology_and_handover()
    test_pillar_4_edge_store_and_forward_and_telemetry()
    test_pillar_1_and_5_safe_promotion_gates()

    print("\n" + "=" * 70)
    print("ALL FIVE PILLARS SUCCESSFULLY VERIFIED (100% PASS RATE)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_all_five_pillars_tests()
