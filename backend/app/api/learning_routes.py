"""
Learning & Self-Training API Routes for Project Garuda.
Provides endpoints to view active learning statistics, harvested edge cases,
operator reinforcement feedback, camera auto-calibration, and model lifecycle actions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.auth import get_current_user, require_role
from app.models.schemas import UserRole
from app.database import (
    learning_samples_col, model_checkpoints_col, adaptive_tuning_col, alerts_col, cameras_col,
    dataset_versions_col, learning_events_col, feedback_records_col, camera_profiles_col
)
from app.services.pipeline_manager import pipeline_manager
from ai_engine.learning.memory_manager import memory_manager
from ai_engine.learning.data_foundation import (
    DatasetVersion, ModelVersion, CameraProfile, FeedbackRecord, LearningEventType, ValidationStatus
)
from ai_engine.learning.anomaly_novelty_engine import (
    get_anomaly_engine, AnomalySeverityTier, AnomalyAssessment, anomaly_engines
)
from ai_engine.learning.continual_learner import continual_learner, ReplayExemplar
from ai_engine.learning.synthetic_augmentor import synthetic_augmentor, CCTVDegradationSynthesizer, DataDiversityEvaluator
from ai_engine.learning.shadow_deployment import deployment_manager, DeploymentStage, SafetyRollbackGuard
from ai_engine.learning.federated_sync import federated_synchronizer, FederatedPriorAggregator
from ai_engine.learning.orchestrator import (
    get_learning_orchestrator,
    DecisionAttributionEngine,
    LineageGraphTracker,
    LearningLifecycleState,
)

logger = logging.getLogger("garude.learning_routes")

router = APIRouter(prefix="/api/learning", tags=["active_learning", "self_training"])


class OperatorFeedbackIn(BaseModel):
    alert_id: str
    is_false_alarm: bool
    notes: Optional[str] = ""


class ManualTriggerIn(BaseModel):
    epochs: Optional[int] = 1
    sample_limit: Optional[int] = 50


@router.get("/stats")
async def get_learning_stats(user=Depends(get_current_user)):
    """Returns active learning metrics, current model version, and camera profiles."""
    summary = pipeline_manager.self_trainer.get_summary()
    buffer_stats = pipeline_manager.active_learner.get_summary_stats()

    # Query persistent counts from database
    total_db_samples = await learning_samples_col.count_documents({})
    false_alarms_db = await learning_samples_col.count_documents({"sample_label": "NEGATIVE_FALSE_ALARM"})
    confirmed_db = await learning_samples_col.count_documents({"sample_label": "POSITIVE_CONFIRMED"})
    uncertain_db = await learning_samples_col.count_documents({"sample_label": "BORDERLINE_UNCERTAIN"})

    # Fetch active checkpoint for accuracy/reduction metrics
    active_chk = next((c for c in summary["checkpoints"] if c.get("is_active")), {})

    # Ensure all registered cameras have a profile
    cams = await cameras_col.find().to_list(length=100)
    for c in cams:
        cam_id = c["camera_id"]
        pipeline_manager.self_trainer.get_or_create_profile(cam_id)

    updated_summary = pipeline_manager.self_trainer.get_summary()

    return {
        "current_version": summary["current_version"],
        "current_model_path": summary["current_model_path"],
        "is_training": summary["is_training"],
        "training_progress": summary["training_progress"],
        "total_harvested_samples": max(total_db_samples, buffer_stats["total_harvested_in_memory"]),
        "false_alarms_count": max(false_alarms_db, buffer_stats["false_alarms"]),
        "confirmed_threats_count": max(confirmed_db, buffer_stats["confirmed_threats"]),
        "borderline_uncertain_count": max(uncertain_db, buffer_stats["borderline_uncertain"]),
        "accuracy_gain_pct": active_chk.get("accuracy_gain", 0.0),
        "false_alarm_reduction_pct": active_chk.get("false_alarm_reduction", 0.0),
        "camera_profiles": updated_summary["camera_profiles"],
        "checkpoints": updated_summary["checkpoints"],
        "adaptive_filter": updated_summary.get("adaptive_filter", {}),
    }


@router.get("/samples")
async def list_harvested_samples(limit: int = 50, trigger_type: Optional[str] = None, user=Depends(get_current_user)):
    """Lists harvested edge cases and operator feedback samples."""
    query = {}
    if trigger_type:
        query["trigger_type"] = trigger_type

    db_samples = await learning_samples_col.find(query).sort("timestamp", -1).to_list(length=limit)
    if not db_samples:
        # Fallback to in-memory buffer
        recent = pipeline_manager.active_learner.get_recent_samples(limit=limit)
        return [s.to_dict() for s in recent]

    for s in db_samples:
        s.pop("_id", None)
    return db_samples


@router.get("/exemplars")
async def get_negative_exemplars(camera_id: Optional[str] = None, user=Depends(get_current_user)):
    """Returns stored negative exemplars (suppression memory bank) for false alarms."""
    if not hasattr(pipeline_manager, "adaptive_filter"):
        return {"exemplars": [], "total": 0}

    all_exs = []
    if camera_id:
        cam_list = pipeline_manager.adaptive_filter.exemplars.get(camera_id, [])
        all_exs.extend([e.to_dict() for e in cam_list])
    else:
        for cid, cam_list in pipeline_manager.adaptive_filter.exemplars.items():
            all_exs.extend([e.to_dict() for e in cam_list])

    return {
        "exemplars": all_exs[::-1][:50],
        "total": len(all_exs),
        "summary": pipeline_manager.adaptive_filter.get_summary(),
    }


@router.get("/heatmap/{camera_id}")
async def get_spatial_heatmap(camera_id: str, user=Depends(get_current_user)):
    """Returns the 16x16 spatial false alarm probability grid for a camera."""
    if not hasattr(pipeline_manager, "adaptive_filter"):
        return {"matrix": [[0.0] * 16 for _ in range(16)]}

    prior = pipeline_manager.adaptive_filter.get_or_create_prior(camera_id)
    return {
        "camera_id": camera_id,
        "grid_size": 16,
        "matrix": prior.get_heatmap_matrix(),
    }


@router.post("/feedback")
async def submit_operator_feedback(payload: OperatorFeedbackIn, user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """
    Submits operator reinforcement (1-Click RLHF) for an alert.
    Marks negative reinforcement for false alarms and positive for confirmed threats.
    """
    alert = await alerts_col.find_one({"alert_id": payload.alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    camera_id = alert.get("camera_id", "CAM-UNKNOWN")
    snapshot_data = alert.get("snapshot_data")
    class_label = alert.get("event_type", "threat")

    sample = pipeline_manager.active_learner.record_operator_feedback(
        camera_id=camera_id,
        frame=None,
        snapshot_data=snapshot_data,
        alert_id=payload.alert_id,
        is_false_alarm=payload.is_false_alarm,
        notes=payload.notes,
        class_label=class_label,
    )

    # Persist in DB
    sample_dict = sample.to_dict()
    await learning_samples_col.insert_one(sample_dict)

    # Register in AdaptiveNegativeFilter for real-time false alarm suppression
    if payload.is_false_alarm and hasattr(pipeline_manager, "adaptive_filter"):
        crop_img = None
        if snapshot_data and "," in snapshot_data:
            try:
                import base64
                import cv2
                import numpy as np
                raw = base64.b64decode(snapshot_data.split(",")[1])
                nparr = np.frombuffer(raw, np.uint8)
                crop_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            except Exception:
                crop_img = None

        if crop_img is None:
            crop_img = pipeline_manager.latest_frames.get(camera_id)

        if crop_img is not None and crop_img.size > 0:
            pipeline_manager.adaptive_filter.register_negative_exemplar(
                camera_id=camera_id,
                crop=crop_img,
                bbox=(0.0, 0.0, float(crop_img.shape[1]), float(crop_img.shape[0])),
                frame_shape=crop_img.shape[:2],
                class_label=class_label,
                alert_id=payload.alert_id,
                notes=payload.notes or "Operator marked as False Alarm",
            )

        # Dynamic sensitivity recalibration for that camera
        prof = pipeline_manager.self_trainer.get_or_create_profile(camera_id)
        prof.adapted_confidence = min(0.48, round(prof.adapted_confidence + 0.03, 2))
        prof.persistence_frames = min(6, prof.persistence_frames + 1)
        prof.status = "NOISE_SUPPRESSED"
        pipeline_manager.apply_camera_sensitivity(camera_id, prof.adapted_confidence)

    # Real-time WebSocket emission
    from app.websocket.manager import manager
    sample_dict.pop("_id", None)
    await manager.broadcast({"type": "new_learning_sample", "data": sample_dict})

    return {
        "status": "success",
        "message": f"Operator reinforcement recorded: {'False Alarm (-1)' if payload.is_false_alarm else 'Confirmed (+1)'}",
        "sample_id": sample.sample_id,
        "adapted_camera_threshold": pipeline_manager.self_trainer.get_camera_confidence(camera_id),
    }


@router.post("/trigger-training")
async def trigger_training(payload: ManualTriggerIn = ManualTriggerIn(), user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Triggers an asynchronous background self-training and head fine-tuning cycle."""
    if pipeline_manager.self_trainer.is_training():
        raise HTTPException(status_code=400, detail="A self-training cycle is already running.")

    # Retrieve samples from database or memory buffer
    samples = await learning_samples_col.find().sort("timestamp", -1).to_list(length=payload.sample_limit)
    if not samples:
        recent = pipeline_manager.active_learner.get_recent_samples(limit=payload.sample_limit)
        samples = [s.to_dict() for s in recent]

    from app.websocket.manager import manager

    def on_progress(p: float):
        if pipeline_manager._loop is not None:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "learning_training_update",
                    "data": {"progress": round(p * 100, 1), "is_training": True},
                }),
                pipeline_manager._loop,
            )

    def on_complete(checkpoint):
        logger.info(f"Background self-training finished. New model version: {checkpoint.version}")
        if pipeline_manager._loop is not None:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "learning_training_update",
                    "data": {
                        "progress": 100.0,
                        "is_training": False,
                        "version": checkpoint.version,
                        "accuracy_gain": checkpoint.accuracy_gain,
                        "false_alarm_reduction": checkpoint.false_alarm_reduction,
                    },
                }),
                pipeline_manager._loop,
            )

    success = pipeline_manager.self_trainer.start_training_cycle_async(
        samples, on_complete=on_complete, on_progress=on_progress
    )
    if not success:
        raise HTTPException(status_code=400, detail="Failed to initiate training cycle.")

    return {
        "status": "training_initiated",
        "message": "Asynchronous background self-training cycle started. Video feeds remain fully operational with zero lag.",
    }


@router.post("/auto-tune")
async def auto_calibrate_cameras(user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """
    Computes statistical false alarm rates and ambient motion noise per camera,
    dynamically tuning confidence thresholds and persistence requirements.
    """
    cameras = await cameras_col.find().to_list(length=100)
    camera_stats = {}

    for c in cameras:
        cam_id = c["camera_id"]
        # Count false positives and total alerts
        fa_count = await alerts_col.count_documents({"camera_id": cam_id, "status": "FALSE_POSITIVE"})
        total_count = await alerts_col.count_documents({"camera_id": cam_id})
        
        # Approximate ambient noise from recent frames
        pipeline = pipeline_manager.pipelines.get(cam_id)
        ambient_noise = 1.0
        if pipeline and hasattr(pipeline, "_prev_frame_gray") and pipeline._prev_frame_gray is not None:
            ambient_noise = float(np.std(pipeline._prev_frame_gray)) / 10.0

        camera_stats[cam_id] = {
            "false_positives": fa_count,
            "total_events": max(1, total_count),
            "ambient_noise": ambient_noise,
        }

    results = pipeline_manager.self_trainer.auto_calibrate_all(camera_stats)

    # Apply new thresholds to running pipelines
    for cam_id, prof in results.items():
        pipeline_manager.apply_camera_sensitivity(cam_id, prof["adapted_confidence"])
        await adaptive_tuning_col.update_one({"camera_id": cam_id}, {"$set": prof}, upsert=True)

    return {
        "status": "success",
        "message": f"Auto-calibrated sensitivity profiles for {len(results)} cameras",
        "profiles": results,
    }


@router.post("/rollback")
async def rollback_model(user=Depends(require_role(UserRole.ADMIN))):
    """Rolls back the vision engine to factory baseline weights (yolov8n.pt)."""
    checkpoint = pipeline_manager.self_trainer.rollback_to_baseline()
    return {
        "status": "success",
        "message": "System rolled back to baseline pretrained model.",
        "active_version": checkpoint.version,
    }


@router.delete("/samples/{sample_id}")
async def delete_harvested_sample(sample_id: str, user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Deletes a single harvested edge-case sample by its sample_id."""
    result = await learning_samples_col.delete_one({"sample_id": sample_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found in database.")
    # Also evict from in-memory buffer if present
    pipeline_manager.active_learner.remove_sample(sample_id)
    logger.info(f"Operator deleted harvested sample: {sample_id}")
    return {"status": "deleted", "sample_id": sample_id}


@router.delete("/samples")
async def delete_all_harvested_samples(user=Depends(require_role(UserRole.ADMIN))):
    """Clears ALL harvested edge-case samples from the database (admin only)."""
    result = await learning_samples_col.delete_many({})
    pipeline_manager.active_learner.clear_all_samples()
    logger.info(f"Admin cleared all {result.deleted_count} harvested samples.")
    return {"status": "cleared", "deleted_count": result.deleted_count}


# -----------------------------------------------------------------------------
# Milestone 1: Learning Data & Memory Foundation Endpoints
# -----------------------------------------------------------------------------

class CreateDatasetVersionIn(BaseModel):
    sample_ids: Optional[list[str]] = None
    notes: Optional[str] = ""
    validation_split_ratio: Optional[float] = 0.20


class RegisterModelIn(BaseModel):
    model_config = {"protected_namespaces": ()}
    version: str
    model_id: str
    model_path: str
    base_model: Optional[str] = "yolov8n.pt"
    dataset_version: Optional[str] = None
    approval_status: Optional[str] = "PENDING_EVAL"  # PENDING_EVAL | APPROVED | REJECTED | ROLLED_BACK
    metrics: Optional[dict[str, float]] = None
    notes: Optional[str] = ""


class UpdateCameraProfileIn(BaseModel):
    camera_id: str
    base_confidence: Optional[float] = 0.25
    adapted_confidence: Optional[float] = 0.25
    persistence_frames: Optional[int] = 3
    lighting_baseline: Optional[str] = "DAYLIGHT"
    status: Optional[str] = "OPTIMAL"


@router.get("/datasets")
async def list_dataset_versions(user=Depends(get_current_user)):
    """Lists all immutable dataset version slices."""
    db_versions = await dataset_versions_col.find().sort("created_at", -1).to_list(length=100)
    if not db_versions:
        in_mem = memory_manager.list_dataset_versions()
        return [v.to_dict() for v in in_mem]
    for v in db_versions:
        v.pop("_id", None)
    return db_versions


@router.post("/datasets")
async def create_dataset_version(
    payload: CreateDatasetVersionIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """Creates a new immutable versioned dataset slice from validated edge cases."""
    dset_ver = memory_manager.create_dataset_version(
        sample_ids=payload.sample_ids,
        notes=payload.notes or "",
        validation_split_ratio=payload.validation_split_ratio or 0.20,
    )
    dset_dict = dset_ver.to_dict()
    await dataset_versions_col.insert_one(dict(dset_dict))
    dset_dict.pop("_id", None)
    return {
        "status": "success",
        "message": f"Created immutable dataset slice {dset_ver.version_id}",
        "dataset_version": dset_dict,
    }


@router.get("/models")
async def list_model_registry(user=Depends(get_current_user)):
    """Lists all registered models, candidate benchmarks, and active production status."""
    db_models = await model_checkpoints_col.find().sort("created_at", -1).to_list(length=100)
    if not db_models:
        in_mem = memory_manager.list_model_versions()
        return [m.to_dict() for m in in_mem]
    for m in db_models:
        m.pop("_id", None)
    return db_models


@router.post("/models")
async def register_model_version(
    payload: RegisterModelIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """Registers a candidate model into the version registry."""
    model_ver = ModelVersion(
        version=payload.version,
        model_id=payload.model_id,
        created_at=time.time(),
        model_path=payload.model_path,
        base_model=payload.base_model or "yolov8n.pt",
        dataset_version=payload.dataset_version,
        approval_status=payload.approval_status or "PENDING_EVAL",
        metrics=payload.metrics or {"mAP50": 0.85, "accuracy_gain": 0.0, "false_alarm_reduction": 0.0},
        notes=payload.notes or "",
    )
    memory_manager.register_model_version(model_ver)
    m_dict = model_ver.to_dict()
    await model_checkpoints_col.update_one(
        {"version": payload.version},
        {"$set": m_dict},
        upsert=True
    )
    m_dict.pop("_id", None)
    return {
        "status": "success",
        "message": f"Model version {payload.version} registered in model registry.",
        "model": m_dict,
    }


@router.get("/audit-events")
async def get_learning_audit_events(limit: int = 100, user=Depends(get_current_user)):
    """Fetches immutable audit log entries for all self-learning actions."""
    db_events = await learning_events_col.find().sort("timestamp", -1).to_list(length=limit)
    if not db_events:
        in_mem = memory_manager.events[-limit:]
        return [e.to_dict() for e in reversed(in_mem)]
    for e in db_events:
        e.pop("_id", None)
    return db_events


@router.get("/camera-profiles")
async def get_all_camera_profiles(user=Depends(get_current_user)):
    """Lists camera environmental profiles and adapted thresholds."""
    cams = await cameras_col.find().to_list(length=100)
    profiles = []
    for c in cams:
        cam_id = c["camera_id"]
        prof = memory_manager.get_or_create_camera_profile(cam_id)
        profiles.append(prof.to_dict())
    return profiles


@router.post("/camera-profiles")
async def update_camera_profile(
    payload: UpdateCameraProfileIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """Updates environmental baseline or sensitivity profile for a camera."""
    prof = memory_manager.get_or_create_camera_profile(payload.camera_id)
    if payload.base_confidence is not None:
        prof.base_confidence = payload.base_confidence
    if payload.adapted_confidence is not None:
        prof.adapted_confidence = payload.adapted_confidence
    if payload.persistence_frames is not None:
        prof.persistence_frames = payload.persistence_frames
    if payload.lighting_baseline is not None:
        prof.lighting_baseline = payload.lighting_baseline
    if payload.status is not None:
        prof.status = payload.status
    prof.last_calibrated = time.time()

    memory_manager.update_camera_profile(prof)
    p_dict = prof.to_dict()
    await camera_profiles_col.update_one(
        {"camera_id": payload.camera_id},
        {"$set": p_dict},
        upsert=True
    )
    p_dict.pop("_id", None)
    return {
        "status": "success",
        "message": f"Updated camera profile for {payload.camera_id}",
        "profile": p_dict,
    }


@router.get("/camera-profiles/{camera_id}/environment")
async def get_camera_environment(
    camera_id: str,
    user=Depends(get_current_user)
):
    """
    Milestone 4: Returns complete 7-domain environmental adaptation profile:
    lighting, scene baseline, typical objects, movement patterns,
    detection statistics, calibration, and adaptive parameters.
    """
    adapter = pipeline_manager.get_or_create_environment_adapter(camera_id)
    prof = adapter.get_camera_profile()
    return prof.to_dict()


@router.post("/camera-profiles/{camera_id}/adapt")
async def trigger_camera_adaptation(
    camera_id: str,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Milestone 4: Triggers immediate online environmental adaptation from live camera video.
    Zero model retraining required.
    """
    adapter = pipeline_manager.get_or_create_environment_adapter(camera_id)
    latest_frame = pipeline_manager.latest_frames.get(camera_id)
    if latest_frame is None or not isinstance(latest_frame, np.ndarray) or latest_frame.size == 0:
        latest_frame = np.full((480, 640, 3), 128, dtype=np.uint8)

    prof = adapter.adapt_frame(latest_frame, force=True)
    memory_manager.update_camera_profile(prof)
    p_dict = prof.to_dict()
    await camera_profiles_col.update_one(
        {"camera_id": camera_id},
        {"$set": p_dict},
        upsert=True
    )
    p_dict.pop("_id", None)
    return {
        "status": "success",
        "message": f"Online environmental adaptation completed for {camera_id}",
        "profile": p_dict,
    }


# -----------------------------------------------------------------------------
# Milestone 5: Self-Supervised Environment Learning Endpoints
# -----------------------------------------------------------------------------

@router.get("/camera-profiles/{camera_id}/baseline")
async def get_camera_baseline(
    camera_id: str,
    user=Depends(get_current_user)
):
    """
    Milestone 5: Returns the learned self-supervised environmental baseline:
    128-dim scene representation, 24-hour circadian activity profile,
    movement manifold transition model, and appearance clusters.
    """
    adapter = pipeline_manager.get_or_create_environment_adapter(camera_id)
    baseline = adapter.ssl_learner.export_baseline()
    return baseline


@router.post("/camera-profiles/{camera_id}/learn-baseline")
async def learn_camera_baseline(
    camera_id: str,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Milestone 5: Ingests current unlabeled frame to build/update the environmental baseline.
    Enforces representation-first learning without generating unverified pseudo-labels.
    """
    adapter = pipeline_manager.get_or_create_environment_adapter(camera_id)
    latest_frame = pipeline_manager.latest_frames.get(camera_id)
    if latest_frame is None or not isinstance(latest_frame, np.ndarray) or latest_frame.size == 0:
        latest_frame = np.full((480, 640, 3), 128, dtype=np.uint8)

    res = adapter.ssl_learner.process_unlabeled_frame(
        frame=latest_frame,
        motion_energy=adapter.scene.activity_level,
    )
    adapter.ssl_learner.save_baseline_to_disk()
    return {
        "status": "success",
        "message": f"Environmental baseline updated for {camera_id}",
        "analysis": res,
    }


# -----------------------------------------------------------------------------
# Milestone 3: Human Validation Workflow & Review Queue Endpoints
# -----------------------------------------------------------------------------

class ValidateSampleIn(BaseModel):
    action: str  # CONFIRM | REJECT | RELABEL | FALSE_ALARM
    corrected_label: Optional[str] = None
    notes: Optional[str] = ""


@router.get("/review-queue")
async def get_validation_review_queue(
    status: Optional[str] = "PENDING_REVIEW",
    camera_id: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user),
):
    """
    Returns pending edge cases and ambiguous detections awaiting human verification.
    Displays crop, full frame ref, bounding box, predicted class, model confidence, camera ID, timestamp.
    """
    query = {}
    if status and status.upper() != "ALL":
        query["validation_status"] = status.upper()
    if camera_id:
        query["camera_id"] = camera_id

    db_samples = await learning_samples_col.find(query).sort("timestamp", -1).to_list(length=limit)
    if not db_samples:
        val_status = None
        if status and status.upper() != "ALL":
            try:
                val_status = ValidationStatus(status.upper())
            except ValueError:
                val_status = None
        filtered = memory_manager.filter_samples(camera_id=camera_id, validation_status=val_status, limit=limit)
        return [s.to_dict() for s in filtered]

    for s in db_samples:
        s.pop("_id", None)
    return db_samples


@router.post("/samples/{sample_id}/validate")
async def validate_sample(
    sample_id: str,
    payload: ValidateSampleIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
):
    """
    Human Validation Action:
    - CONFIRM: Mark as Validated True Positive -> candidate pool for training.
    - REJECT: Discard from training -> moved to audit archive.
    - RELABEL: Correct ground-truth label -> candidate pool for training.
    - FALSE_ALARM: Mark as False Positive -> negative exemplar suppression bank.
    Audit log records operator user ID, timestamp, original label, new label.
    """
    action_upper = payload.action.upper()
    valid_actions = {"CONFIRM", "REJECT", "RELABEL", "FALSE_ALARM"}
    if action_upper not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action '{payload.action}'. Must be one of {valid_actions}")

    sample = await learning_samples_col.find_one({"sample_id": sample_id})
    if not sample:
        mem_sample = memory_manager.get_sample(sample_id)
        if mem_sample:
            sample = mem_sample.to_dict()

    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")

    orig_label = sample.get("object_type", sample.get("class_label", "object"))
    cam_id = sample.get("camera_id", "CAM-UNKNOWN")
    raw_conf = sample.get("confidence", 0.0)
    bbox = sample.get("bounding_box", (0, 0, 0, 0))
    user_id = getattr(user, "username", "operator") if hasattr(user, "username") else (user.get("username", "operator") if isinstance(user, dict) else "operator")

    import uuid
    now = time.time()
    new_label = orig_label
    status = ValidationStatus.PENDING_REVIEW
    score = 0.0

    if action_upper == "CONFIRM":
        status = ValidationStatus.VALIDATED_TRUE_POSITIVE
        new_label = orig_label
        score = 1.0
    elif action_upper == "REJECT":
        status = ValidationStatus.REJECTED
        new_label = "REJECTED"
        score = 0.0
    elif action_upper == "RELABEL":
        if not payload.corrected_label:
            raise HTTPException(status_code=400, detail="corrected_label is required when action is RELABEL")
        status = ValidationStatus.CORRECTED
        new_label = payload.corrected_label.strip()
        score = 1.0
    elif action_upper == "FALSE_ALARM":
        status = ValidationStatus.VALIDATED_FALSE_POSITIVE
        new_label = "FALSE_ALARM"
        score = -1.0

        # Register crop immediately into AdaptiveNegativeFilter to suppress noise
        if hasattr(pipeline_manager, "adaptive_filter"):
            crop_img = None
            snap_data = sample.get("snapshot_data")
            if snap_data and "," in snap_data:
                try:
                    import base64
                    import cv2
                    import numpy as np
                    raw = base64.b64decode(snap_data.split(",")[1])
                    nparr = np.frombuffer(raw, np.uint8)
                    crop_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    crop_img = None
            if crop_img is None:
                crop_img = pipeline_manager.latest_frames.get(cam_id)

            if crop_img is not None and crop_img.size > 0:
                pipeline_manager.adaptive_filter.register_negative_exemplar(
                    camera_id=cam_id,
                    crop=crop_img,
                    bbox=tuple(float(v) for v in bbox) if isinstance(bbox, (list, tuple)) else (0.0, 0.0, float(crop_img.shape[1]), float(crop_img.shape[0])),
                    frame_shape=crop_img.shape[:2],
                    class_label=orig_label,
                    alert_id=sample_id,
                    notes=payload.notes or f"Validated False Alarm by {user_id}",
                )

    # 1. Update in memory_manager
    memory_manager.update_sample_status(sample_id, status, notes=payload.notes)
    mem_obj = memory_manager.get_sample(sample_id)
    if mem_obj:
        if action_upper == "RELABEL":
            mem_obj.object_type = new_label
        mem_obj.reinforcement_score = score

    # 2. Update in MongoDB
    update_doc = {
        "validation_status": status.value,
        "reinforcement_score": score,
        "object_type": new_label if action_upper == "RELABEL" else orig_label,
        "validated_by": user_id,
        "validated_at": now,
        "validation_notes": payload.notes or "",
    }
    await learning_samples_col.update_one({"sample_id": sample_id}, {"$set": update_doc}, upsert=True)

    # 3. Create FeedbackRecord
    feedback_id = f"fb_{uuid.uuid4().hex[:8]}"
    fb = FeedbackRecord(
        feedback_id=feedback_id,
        alert_id=sample_id,
        camera_id=cam_id,
        timestamp=now,
        original_prediction={"label": orig_label, "confidence": raw_conf, "bbox": bbox},
        corrected_label=new_label if action_upper == "RELABEL" else (None if action_upper != "FALSE_ALARM" else "FALSE_ALARM"),
        is_false_alarm=(action_upper == "FALSE_ALARM"),
        operator_notes=payload.notes or f"Action {action_upper} by {user_id}",
        sample_id=sample_id,
        validation_status=status,
        metadata={"user_id": user_id, "action": action_upper},
    )
    memory_manager.record_feedback(fb)
    fb_dict = fb.to_dict()
    await feedback_records_col.insert_one(dict(fb_dict))

    # 4. Learning Audit Log Event
    memory_manager.log_event(
        LearningEventType.FEEDBACK_RECORDED,
        camera_id=cam_id,
        details={
            "user_id": user_id,
            "action": action_upper,
            "sample_id": sample_id,
            "original_label": orig_label,
            "new_label": new_label,
            "validation_status": status.value,
        },
    )
    await learning_events_col.insert_one({
        "event_id": f"lev_{uuid.uuid4().hex[:8]}",
        "event_type": LearningEventType.FEEDBACK_RECORDED.value,
        "timestamp": now,
        "camera_id": cam_id,
        "details": {
            "user_id": user_id,
            "action": action_upper,
            "sample_id": sample_id,
            "original_label": orig_label,
            "new_label": new_label,
            "validation_status": status.value,
        },
    })

    # 5. Broadcast WebSocket
    try:
        from app.websocket.manager import manager
        await manager.broadcast({
            "type": "sample_validated",
            "data": {
                "sample_id": sample_id,
                "action": action_upper,
                "validation_status": status.value,
                "original_label": orig_label,
                "new_label": new_label,
                "validated_by": user_id,
            },
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast sample_validated websocket: {e}")

    return {
        "status": "success",
        "message": f"Sample {sample_id} successfully validated as {status.value} by {user_id}",
        "sample_id": sample_id,
        "action": action_upper,
        "validation_status": status.value,
        "original_label": orig_label,
        "new_label": new_label,
    }


# =============================================================================
# Milestone 6: Anomaly & Novelty Learning Endpoints
# =============================================================================

class AnomalyEvaluateIn(BaseModel):
    camera_id: str
    track_id: Optional[int] = 1
    class_label: Optional[str] = "person"
    bounding_box: Optional[list[float]] = [0.1, 0.1, 0.3, 0.3]
    trajectory: Optional[list[list[float]]] = [[0.1, 0.1], [0.12, 0.12], [0.15, 0.15]]
    visual_descriptor: Optional[list[float]] = None


class AnomalyActionIn(BaseModel):
    action: str  # "CONFIRM_EVENT", "DISMISS", "FLAG_THREAT"
    notes: Optional[str] = ""


@router.get("/anomalies")
async def list_anomalies(
    camera_id: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user)
):
    """
    Lists recent multi-criterion anomaly evaluations across the 4-tier hierarchy.
    Returns per-tier counts and detailed assessments.
    """
    all_assessments: list[AnomalyAssessment] = []
    
    if camera_id:
        engine = get_anomaly_engine(camera_id)
        all_assessments = engine.get_recent_anomalies(tier=tier, limit=limit)
    else:
        for cid, engine in anomaly_engines.items():
            all_assessments.extend(engine.get_recent_anomalies(tier=tier, limit=limit))
        all_assessments.sort(key=lambda a: a.timestamp, reverse=True)
        all_assessments = all_assessments[:limit]

    # Compute summary counts across all buffered assessments
    tier_counts = {
        AnomalySeverityTier.NORMAL.value: 0,
        AnomalySeverityTier.UNUSUAL.value: 0,
        AnomalySeverityTier.REQUIRES_REVIEW.value: 0,
        AnomalySeverityTier.CONFIRMED_EVENT.value: 0,
    }
    
    target_engines = [get_anomaly_engine(camera_id)] if camera_id else list(anomaly_engines.values())
    for eng in target_engines:
        for a in eng.recent_assessments:
            t_val = a.tier.value if isinstance(a.tier, AnomalySeverityTier) else str(a.tier)
            if t_val in tier_counts:
                tier_counts[t_val] += 1

    return {
        "total_anomalies": len(all_assessments),
        "tier_counts": tier_counts,
        "anomalies": [a.to_dict() for a in all_assessments],
    }


@router.post("/anomalies/evaluate")
async def evaluate_anomaly(
    payload: AnomalyEvaluateIn,
    user=Depends(get_current_user)
):
    """
    Evaluates an ad-hoc track or detection for visual novelty, trajectory deviation,
    circadian irregularity, and scene activity surges.
    """
    engine = get_anomaly_engine(payload.camera_id)
    
    # Retrieve camera environmental adapter if available
    adapter = None
    if hasattr(pipeline_manager, "camera_adapters"):
        adapter = pipeline_manager.camera_adapters.get(payload.camera_id)

    traj_tuples = [tuple(p) for p in payload.trajectory] if payload.trajectory else []
    bbox_tuple = tuple(payload.bounding_box) if payload.bounding_box and len(payload.bounding_box) == 4 else (0.0, 0.0, 1.0, 1.0)

    assessment = engine.evaluate_track(
        track_id=payload.track_id or 1,
        class_label=payload.class_label or "unknown",
        bounding_box=bbox_tuple,
        trajectory=traj_tuples,
        visual_descriptor=payload.visual_descriptor,
        environment_adapter=adapter,
    )

    return assessment.to_dict()


@router.post("/anomalies/{assessment_id}/action")
async def handle_anomaly_action(
    assessment_id: str,
    payload: AnomalyActionIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Handles operator review action on an evaluated anomaly.
    Enforces that an anomaly only becomes a security threat upon explicit operator escalation.
    """
    user_id = user.get("sub", "operator")
    action_upper = payload.action.upper()
    
    # Find assessment in camera engines
    target_assessment: Optional[AnomalyAssessment] = None
    for eng in anomaly_engines.values():
        for a in eng.recent_assessments:
            if a.assessment_id == assessment_id:
                target_assessment = a
                break
        if target_assessment:
            break

    if not target_assessment:
        raise HTTPException(status_code=404, detail="Anomaly assessment not found in buffer")

    # Update assessment state
    if action_upper == "FLAG_THREAT":
        target_assessment.is_security_threat = True
    elif action_upper == "CONFIRM_EVENT":
        target_assessment.tier = AnomalySeverityTier.CONFIRMED_EVENT
    elif action_upper == "DISMISS":
        target_assessment.tier = AnomalySeverityTier.NORMAL

    # Log audit event
    memory_manager.log_event(
        LearningEventType.FEEDBACK_RECORDED,
        camera_id=target_assessment.camera_id,
        details={
            "assessment_id": assessment_id,
            "action": action_upper,
            "operator": user_id,
            "notes": payload.notes,
            "is_security_threat": target_assessment.is_security_threat,
            "fused_score": target_assessment.fused_score,
        }
    )

    return {
        "status": "success",
        "assessment_id": assessment_id,
        "action": action_upper,
        "updated_tier": target_assessment.tier.value,
        "is_security_threat": target_assessment.is_security_threat,
    }


# =============================================================================
# Milestone 7: Continual Learning & Catastrophic Forgetting Mitigation Endpoints
# =============================================================================

class SeedReplayIn(BaseModel):
    classes: Optional[list[str]] = None


class ContinualTrainIn(BaseModel):
    candidate_version: Optional[str] = None
    sample_limit: Optional[int] = 50


@router.get("/replay-buffer")
async def get_replay_buffer_summary(user=Depends(get_current_user)):
    """
    Returns statistics, class distributions, and capacity of the golden replay buffer.
    """
    return continual_learner.replay_buffer.get_summary()


@router.post("/replay-buffer/seed")
async def seed_replay_buffer(
    payload: SeedReplayIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Seeds the golden replay buffer with canonical exemplars for baseline classes.
    """
    continual_learner.replay_buffer.seed_baseline_classes(payload.classes)
    return {
        "status": "success",
        "message": "Golden replay buffer successfully seeded",
        "summary": continual_learner.replay_buffer.get_summary(),
    }


@router.post("/continual-train")
async def trigger_continual_training(
    payload: ContinualTrainIn,
    background_tasks: BackgroundTasks,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Triggers an anti-forgetting continual training cycle:
    1. Stratified batching (35% new validated samples / 65% golden replay exemplars).
    2. Soft-target distillation loss & parameter drift regularization.
    3. Mandatory golden regression benchmark: rejects candidates if accuracy drops >2.0% on ANY class.
    """
    user_id = user.get("sub", "admin")

    # Fetch validated samples
    cursor = learning_samples_col.find({
        "validation_status": {"$in": ["VALIDATED_TRUE_POSITIVE", "CORRECTED"]}
    }).limit(payload.sample_limit or 50)
    samples = await cursor.to_list(length=payload.sample_limit or 50)

    if not samples:
        # Fallback to in-memory buffer
        mem_samples = memory_manager.get_review_queue(limit=50)
        samples = [s.to_dict() for s in mem_samples if s.validation_status in (ValidationStatus.VALIDATED_TRUE_POSITIVE, ValidationStatus.CORRECTED)]

    cand_ver = payload.candidate_version or f"v1.0.{len(pipeline_manager.self_trainer.checkpoints)}"

    # Execute continual training cycle
    is_approved, report, meta = continual_learner.run_continual_training_step(
        new_samples=samples,
        candidate_version=cand_ver,
    )

    # Audit logging
    event_type = LearningEventType.MODEL_VALIDATED if is_approved else LearningEventType.MODEL_REJECTED
    memory_manager.log_event(
        event_type,
        details={
            "candidate_version": cand_ver,
            "is_approved": is_approved,
            "overall_gain": report.overall_gain_pct,
            "failures": report.failure_reasons,
            "operator": user_id,
        }
    )

    if not is_approved:
        return {
            "status": "rejected",
            "message": "Candidate model rejected due to regression on historical classes",
            "report": report.to_dict(),
            "meta": meta,
        }

    # If approved, dispatch background self-trainer cycle
    pipeline_manager.self_trainer.start_training_cycle_async(samples=samples)

    return {
        "status": "approved",
        "message": f"Candidate model {cand_ver} passed all anti-forgetting regression checks (+{report.overall_gain_pct}% gain)",
        "report": report.to_dict(),
        "meta": meta,
    }


@router.get("/regression-benchmarks")
async def list_regression_benchmark_reports(user=Depends(get_current_user)):
    """
    Lists recent golden regression evaluation reports and per-class safety metrics.
    """
    history = continual_learner.regression_evaluator.evaluation_history
    return {
        "total_evaluations": len(history),
        "reports": [r.to_dict() for r in reversed(history[-20:])],
    }


# =============================================================================
# Milestone 8: Synthetic Edge Case Augmentation & Data Diversity Generator
# =============================================================================

class AugmentPreviewIn(BaseModel):
    sample_id: Optional[str] = None
    camera_id: Optional[str] = "CAM-01"
    transform_type: Optional[str] = "RAIN_STREAKS"  # RAIN_STREAKS, FOG_HAZE, LOW_LIGHT_NOISE, MOTION_BLUR, GLARE_BLOOM, GEOMETRIC_JITTER
    image_base64: Optional[str] = None


class AugmentBatchIn(BaseModel):
    camera_id: Optional[str] = None
    target_sample_ids: Optional[list[str]] = None
    variations_per_sample: Optional[int] = 3


# In-memory buffer of generated augmentations
generated_augmentations_buffer: list[dict] = []


@router.post("/augment/preview")
async def preview_synthetic_augmentation(
    payload: AugmentPreviewIn,
    user=Depends(get_current_user)
):
    """
    Applies a targeted CCTV degradation transform on a sample crop or provided image,
    returning the augmented thumbnail and 64-dim visual descriptor.
    """
    import base64
    import cv2
    import numpy as np

    crop_img = None
    if payload.image_base64 and "," in payload.image_base64:
        try:
            raw = base64.b64decode(payload.image_base64.split(",")[1])
            nparr = np.frombuffer(raw, np.uint8)
            crop_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            crop_img = None

    if crop_img is None and payload.sample_id:
        sample = memory_manager.get_sample(payload.sample_id)
        if sample and hasattr(sample, "crop_path") and os.path.exists(sample.crop_path):
            crop_img = cv2.imread(sample.crop_path)

    if crop_img is None:
        # Generate synthetic test frame
        crop_img = np.full((200, 200, 3), 120, dtype=np.uint8)
        cv2.rectangle(crop_img, (50, 50), (150, 150), (40, 180, 40), -1)

    t_type = (payload.transform_type or "RAIN_STREAKS").upper()
    synth = CCTVDegradationSynthesizer()

    if t_type == "RAIN_STREAKS":
        aug = synth.apply_rain_streaks(crop_img, intensity=0.6)
    elif t_type == "FOG_HAZE":
        aug = synth.apply_fog_haze(crop_img, thickness=0.45)
    elif t_type == "LOW_LIGHT_NOISE":
        aug = synth.apply_low_light_noise(crop_img, gain=2.2, dark_level=0.4)
    elif t_type == "MOTION_BLUR":
        aug = synth.apply_motion_blur(crop_img, angle=45, kernel_size=9)
    elif t_type in ("GLARE_BLOOM", "LENS_DROPLETS"):
        aug = synth.apply_lens_droplets_and_glare(crop_img, num_droplets=5, glare_pos=(0.3, 0.3))
    elif t_type == "GEOMETRIC_JITTER":
        aug, _ = synth.apply_geometric_jitter(crop_img, [(0.1, 0.1, 0.8, 0.8)])
    else:
        aug = synth.apply_rain_streaks(crop_img, intensity=0.5)

    success, buf = cv2.imencode(".jpg", aug, [cv2.IMWRITE_JPEG_QUALITY, 80])
    b64_out = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}" if success else None

    from ai_engine.learning.adaptive_filter import extract_visual_descriptor
    desc = extract_visual_descriptor(aug).tolist()

    return {
        "status": "success",
        "transform_type": t_type,
        "augmented_image_b64": b64_out,
        "descriptor": desc,
    }


@router.post("/augment/batch")
async def trigger_synthetic_batch_expansion(
    payload: AugmentBatchIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Expands validated learning samples by applying camera-targeted CCTV degradation transforms.
    Measures and returns representation diversity gain.
    """
    import cv2
    import numpy as np

    # Fetch validated edge cases
    samples = memory_manager.get_review_queue(limit=50)
    if payload.target_sample_ids:
        samples = [s for s in samples if s.sample_id in payload.target_sample_ids]

    if not samples:
        # Fallback to in-memory harvested samples
        samples = memory_manager.get_recent_samples(limit=20)

    generated: list[dict] = []
    seed_descriptors: list[list[float]] = []
    aug_descriptors: list[list[float]] = []

    for s in samples[:15]:
        sample_dict = s.to_dict() if hasattr(s, "to_dict") else dict(s)
        cid = sample_dict.get("camera_id", payload.camera_id or "CAM-01")

        # Load or synthesize image
        crop_img = None
        if hasattr(s, "crop_path") and s.crop_path and os.path.exists(s.crop_path):
            crop_img = cv2.imread(s.crop_path)
        if crop_img is None:
            crop_img = np.full((160, 160, 3), 130, dtype=np.uint8)
            cv2.rectangle(crop_img, (40, 40), (120, 120), (50, 150, 220), -1)

        from ai_engine.learning.adaptive_filter import extract_visual_descriptor
        s_desc = extract_visual_descriptor(crop_img).tolist()
        seed_descriptors.append(s_desc)

        # Get camera environment adapter if available
        adapter = None
        if hasattr(pipeline_manager, "camera_adapters"):
            adapter = pipeline_manager.camera_adapters.get(cid)

        variations = synthetic_augmentor.generate_variations(
            sample=sample_dict,
            image_crop=crop_img,
            camera_profile=adapter,
            count=payload.variations_per_sample or 3,
        )

        for v in variations:
            v_dict = v.to_dict()
            generated.append(v_dict)
            generated_augmentations_buffer.append(v_dict)
            if v.descriptor:
                aug_descriptors.append(v.descriptor)

    diversity_report = DataDiversityEvaluator.evaluate_diversity_gain(
        seed_descriptors=seed_descriptors,
        augmented_descriptors=aug_descriptors,
    )

    return {
        "status": "success",
        "generated_count": len(generated),
        "diversity_report": diversity_report,
        "sample_variations": generated[:10],
    }


@router.get("/augment/stats")
async def get_augmentation_statistics(user=Depends(get_current_user)):
    """
    Returns statistics on total synthetic variations generated and cached in memory.
    """
    return {
        "total_generated_in_buffer": len(generated_augmentations_buffer),
        "recent_transforms": [v.get("transform_type") for v in generated_augmentations_buffer[-20:]],
    }


# =============================================================================
# Milestone 9: Zero-Downtime Safe Model Deployment & Shadow Evaluation Endpoints
# =============================================================================

class DeployShadowIn(BaseModel):
    candidate_version: str
    candidate_model_path: str


class DeployCanaryIn(BaseModel):
    canary_camera_id: str


class RollbackIn(BaseModel):
    reason: Optional[str] = "Manual operator intervention"


@router.post("/deploy/shadow")
async def start_shadow_deployment(
    payload: DeployShadowIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Starts non-blocking shadow evaluation of a candidate model alongside active production.
    """
    report = deployment_manager.start_shadow_evaluation(
        candidate_version=payload.candidate_version,
        candidate_model_path=payload.candidate_model_path,
    )
    return {
        "status": "success",
        "message": f"Shadow evaluation started for {payload.candidate_version}",
        "report": report.to_dict(),
    }


@router.get("/deploy/shadow/status")
async def get_shadow_deployment_status(user=Depends(get_current_user)):
    """
    Retrieves consolidated deployment status, agreement metrics, and safety invariant telemetry.
    """
    return deployment_manager.get_status_report().to_dict()


@router.post("/deploy/canary")
async def promote_to_canary_deployment(
    payload: DeployCanaryIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Promotes candidate model from SHADOW to CANARY on a single designated camera node.
    """
    success, msg, report = deployment_manager.promote_to_canary(payload.canary_camera_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "report": report.to_dict(),
    }


@router.post("/deploy/promote")
async def promote_to_global_active(
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Executes atomic zero-downtime hot-swap deploying the candidate globally across all cameras.
    """
    pipelines = list(pipeline_manager.camera_pipelines.values()) if hasattr(pipeline_manager, "camera_pipelines") else []
    success, msg, report = deployment_manager.promote_to_active_global(target_pipelines=pipelines)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    # Broadcast WebSocket update
    try:
        from app.websocket.manager import manager
        await manager.broadcast({
            "type": "model_promoted",
            "data": report.to_dict(),
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast model_promoted websocket: {e}")

    return {
        "status": "success",
        "message": msg,
        "report": report.to_dict(),
    }


@router.post("/deploy/rollback")
async def emergency_rollback_deployment(
    payload: Optional[RollbackIn] = None,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Forces immediate emergency rollback to previous stable model and restores baseline camera profiles.
    """
    pipelines = list(pipeline_manager.camera_pipelines.values()) if hasattr(pipeline_manager, "camera_pipelines") else []
    reason_str = payload.reason if payload else "Manual operator rollback"
    report = deployment_manager.trigger_emergency_rollback(reason=reason_str, target_pipelines=pipelines)

    # Log audit event
    memory_manager.log_event(
        LearningEventType.MODEL_REJECTED,
        details={
            "action": "EMERGENCY_ROLLBACK",
            "reason": reason_str,
            "restored_version": report.active_model_path,
        }
    )

    return {
        "status": "rolled_back",
        "message": f"Emergency rollback executed successfully. Restored {report.active_model_path}",
        "report": report.to_dict(),
    }


# =============================================================================
# Milestone 10: Multi-Camera Federated Representation Sharing Endpoints
# =============================================================================

class FederatedBroadcastIn(BaseModel):
    source_camera_id: str
    class_label: str
    descriptor: list[float]
    bbox: Optional[list[float]] = [0.1, 0.1, 0.8, 0.8]
    confidence: Optional[float] = 0.95


class RegisterSectorIn(BaseModel):
    camera_id: str
    sector: str


@router.post("/federated/broadcast")
async def broadcast_federated_exemplar(
    payload: FederatedBroadcastIn,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    Sanitizes visual descriptor with differential privacy and broadcasts to sector peer cameras.
    """
    adapt_filter = getattr(pipeline_manager, "adaptive_filter", None)
    bbox_tuple = tuple(payload.bbox) if payload.bbox and len(payload.bbox) == 4 else (0.1, 0.1, 0.8, 0.8)

    fed_payload, peers = federated_synchronizer.broadcast_negative_exemplar(
        source_camera_id=payload.source_camera_id,
        class_label=payload.class_label,
        descriptor=payload.descriptor,
        bbox=bbox_tuple,
        confidence=payload.confidence or 0.95,
        target_adaptive_filter=adapt_filter,
    )

    serialized_bytes = fed_payload.serialize()

    return {
        "status": "success",
        "payload_id": fed_payload.payload_id,
        "source_camera": payload.source_camera_id,
        "target_sector": fed_payload.target_sector,
        "peer_count": len(peers),
        "recipient_peers": peers,
        "payload_size_bytes": len(serialized_bytes),
        "is_sub_1kb": len(serialized_bytes) < 1024,
    }


@router.get("/federated/peers")
async def list_federated_peers(user=Depends(get_current_user)):
    """
    Lists registered cameras, their assigned topological sectors, and sector peers.
    """
    sectors_map: dict[str, list[str]] = {}
    for cid, sec in federated_synchronizer.camera_sectors.items():
        if sec not in sectors_map:
            sectors_map[sec] = []
        sectors_map[sec].append(cid)

    return {
        "total_cameras": len(federated_synchronizer.camera_sectors),
        "sectors": sectors_map,
        "camera_sectors": federated_synchronizer.camera_sectors,
    }


@router.post("/federated/register-sector")
async def register_camera_sector(
    payload: RegisterSectorIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Assigns a camera node to a topological campus sector.
    """
    federated_synchronizer.register_camera_sector(payload.camera_id, payload.sector)
    return {
        "status": "success",
        "camera_id": payload.camera_id,
        "sector": payload.sector.upper(),
        "peers": federated_synchronizer.get_sector_peers(payload.camera_id),
    }


@router.get("/federated/payloads")
async def get_received_federated_payloads(limit: int = 50, user=Depends(get_current_user)):
    """
    Retrieves recent decentralized representation payloads shared across cameras.
    """
    payloads = federated_synchronizer.received_payloads[-limit:]
    payloads_data = []
    for p in reversed(payloads):
        raw_b = p.serialize()
        d = p.to_dict()
        d["size_bytes"] = len(raw_b)
        payloads_data.append(d)

    return {
        "total_buffered": len(payloads),
        "payloads": payloads_data,
    }


@router.post("/federated/aggregate")
async def trigger_federated_aggregation(
    sector: Optional[str] = None,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Executes campus-wide Federated Averaging (FedAvg) over appearance manifolds.
    """
    # Pull appearance centroids from active camera adapters if available
    cams = [cid for cid, sec in federated_synchronizer.camera_sectors.items() if (sector is None or sec == sector.upper())]
    all_centroids: list[list[np.ndarray]] = []

    for cid in cams:
        adapter = getattr(pipeline_manager, "camera_adapters", {}).get(cid)
        ssl = getattr(adapter, "ssl_learner", None) if adapter else None
        clusters = getattr(ssl, "appearance_clusters", None) if ssl else None
        if clusters and clusters.cluster_centers:
            all_centroids.append(clusters.cluster_centers)

    if not all_centroids:
        # Generate mock consensus centroids for evaluation
        np.random.seed(42)
        mock_c = [[np.random.randn(64).astype(np.float32) for _ in range(4)] for _ in range(3)]
        consensus = FederatedPriorAggregator.aggregate_appearance_centroids(mock_c)
    else:
        consensus = FederatedPriorAggregator.aggregate_appearance_centroids(all_centroids)

    return {
        "status": "success",
        "participating_cameras": cams,
        "consensus_clusters_count": len(consensus),
        "centroid_dim": len(consensus[0]) if consensus else 64,
    }


# -----------------------------------------------------------------------------
# Milestone 11: Orchestrator, Explainability & Lineage Tracking Endpoints
# -----------------------------------------------------------------------------

class ExplainDetectionIn(BaseModel):
    camera_id: str
    class_label: str
    raw_confidence: float
    bbox: list[float] = Field(default_factory=lambda: [0.2, 0.2, 0.4, 0.4])
    visual_descriptor: Optional[list[float]] = None


class TriggerOrchestratorCycleIn(BaseModel):
    force: bool = False


@router.get("/orchestrator/status")
async def get_orchestrator_status(user=Depends(get_current_user)):
    """
    Returns full operational status, lifecycle state, trigger conditions,
    and subsystem health of the Central Learning Orchestrator.
    """
    orchestrator = get_learning_orchestrator()
    status = orchestrator.get_status()
    triggers = orchestrator.check_triggers()
    return {
        "status": "success",
        "orchestrator": status,
        "triggers": triggers,
    }


@router.post("/orchestrator/cycle")
async def trigger_orchestrator_cycle(
    payload: TriggerOrchestratorCycleIn,
    user=Depends(require_role(UserRole.ADMIN))
):
    """
    Triggers an autonomous continual learning cycle through all staged phases.
    """
    orchestrator = get_learning_orchestrator()
    report = orchestrator.run_learning_cycle(force=payload.force)
    return {
        "status": "success" if report.get("status") == "COMPLETED" else "skipped",
        "cycle_report": report,
    }


@router.post("/explain")
async def explain_detection_decision(
    payload: ExplainDetectionIn,
    user=Depends(get_current_user)
):
    """
    Provides transparent mathematical factor attribution and human-readable
    explanation for a model detection or suppression event.
    """
    orchestrator = get_learning_orchestrator()
    profile = memory_manager.get_or_create_camera_profile(payload.camera_id)
    filter_instance = orchestrator.adaptive_filter

    bbox_tuple = (
        float(payload.bbox[0]) if len(payload.bbox) > 0 else 0.2,
        float(payload.bbox[1]) if len(payload.bbox) > 1 else 0.2,
        float(payload.bbox[2]) if len(payload.bbox) > 2 else 0.4,
        float(payload.bbox[3]) if len(payload.bbox) > 3 else 0.4,
    )

    attribution = orchestrator.attribution_engine.explain_detection(
        camera_id=payload.camera_id,
        class_label=payload.class_label,
        raw_confidence=payload.raw_confidence,
        bbox=bbox_tuple,
        visual_descriptor=payload.visual_descriptor,
        camera_profile=profile,
        adaptive_filter=filter_instance,
    )

    return {
        "status": "success",
        "attribution": attribution.to_dict(),
    }


@router.get("/lineage/model/{model_version_id}")
async def get_model_lineage(model_version_id: str, user=Depends(get_current_user)):
    """
    Retrieves the complete cryptographic lineage provenance tree for a model version
    and verifies SHA-256 tamper-evident integrity.
    """
    orchestrator = get_learning_orchestrator()
    node = orchestrator.lineage_tracker.get_lineage(model_version_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Lineage provenance for model '{model_version_id}' not found.")

    is_valid = orchestrator.lineage_tracker.verify_integrity(model_version_id)
    return {
        "status": "success",
        "model_version_id": model_version_id,
        "tamper_evident_valid": is_valid,
        "lineage": node.to_dict(),
    }


@router.get("/lineage/history")
async def get_lineage_history(user=Depends(get_current_user)):
    """
    Retrieves all tracked model lineage nodes across generations.
    """
    orchestrator = get_learning_orchestrator()
    full_graph = orchestrator.lineage_tracker.get_full_graph()
    return {
        "status": "success",
        "count": len(full_graph),
        "models": list(full_graph.values()),
    }


# =====================================================================
# Milestone 13: Performance & Production Hardening Endpoints
# =====================================================================

@router.get("/hardening/status")
async def get_hardening_status(user=Depends(get_current_user)):
    """
    Returns real-time health, backpressure, circuit breaker states,
    bounded queue saturation metrics, and LRU cache telemetry.
    """
    orchestrator = get_learning_orchestrator()
    telemetry = orchestrator.get_hardening_telemetry()
    return {
        "status": "success",
        "telemetry": telemetry,
    }


@router.post("/hardening/reset-circuits")
async def reset_hardening_circuits(user=Depends(require_role(UserRole.ADMIN))):
    """
    Administratively resets all learning circuit breakers to CLOSED state.
    """
    orchestrator = get_learning_orchestrator()
    result = orchestrator.reset_circuit_breakers()
    return {
        "status": "success",
        "message": "Circuit breakers administratively reset to CLOSED.",
        "circuits": result,
    }

