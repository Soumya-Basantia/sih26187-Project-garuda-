"""
Attendance/Entry system API endpoints.

Provides logging and retrieval for face-verified entry events.
Entry cameras are marked as "ENTRY_GATE" zone type, triggering attendance logs.
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from datetime import datetime, timedelta

from ..database import db, attendance_entries_col, cameras_col, identities_col
from ..models.schemas import AttendanceEntryOut, UserRole
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


async def get_camera_name(camera_id: str) -> Optional[str]:
    """Get camera name by ID."""
    camera = await cameras_col.find_one({"camera_id": camera_id})
    return camera.get("name") if camera else None


async def get_identity_by_id(identity_id: str) -> Optional[dict]:
    """Get identity by ID."""
    return await identities_col.find_one({"identity_id": identity_id})


@router.post("/log-entry", response_model=dict)
async def log_attendance_entry(
    camera_id: str,
    identity_id: Optional[str] = None,
    verification_confidence: float = 0.0,
    snapshot_path: Optional[str] = None,
    entry_type: str = "FACE_VERIFIED",
    notes: Optional[str] = None,
    _user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
):
    """
    Log an attendance entry (called by event engine when face verification occurs).
    Typically not called directly from frontend.
    """
    # Get camera name
    camera_name = await get_camera_name(camera_id)

    # Get identity details if recognized
    identity_name = None
    identity_role = None
    if identity_id:
        identity = await get_identity_by_id(identity_id)
        if identity:
            identity_name = identity.get('name')
            identity_role = identity.get('role')

    # Create entry document
    entry = {
        'entry_id': f"ent_{int(datetime.now().timestamp() * 1000)}",
        'camera_id': camera_id,
        'camera_name': camera_name or camera_id,
        'identity_id': identity_id,
        'identity_name': identity_name,
        'identity_role': identity_role,
        'verification_confidence': verification_confidence,
        'snapshot_path': snapshot_path,
        'timestamp': datetime.now().timestamp(),
        'entry_type': entry_type,
        'notes': notes or f"Entry at camera {camera_id}"
    }

    await attendance_entries_col.insert_one(entry)

    return {
        'success': True,
        'entry_id': entry['entry_id'],
        'timestamp': entry['timestamp'],
        'identity_recognized': identity_id is not None
    }


@router.get("/entries", response_model=List[AttendanceEntryOut])
async def list_attendance_entries(
    camera_id: Optional[str] = Query(None, description="Filter by camera"),
    identity_id: Optional[str] = Query(None, description="Filter by identity"),
    entry_type: Optional[str] = Query(None, description="Filter by entry type"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, description="Max entries to return"),
    user=Depends(get_current_user),
):
    """
    Retrieve attendance/entry logs with optional filtering.
    """
    query = {}

    if camera_id:
        query['camera_id'] = camera_id

    if identity_id:
        query['identity_id'] = identity_id

    if entry_type:
        query['entry_type'] = entry_type

    # Date range filtering
    if from_date or to_date:
        timestamp_query = {}
        try:
            if from_date:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                timestamp_query['$gte'] = from_dt.timestamp()
            if to_date:
                to_dt = datetime.strptime(to_date, "%Y-%m-%d")
                to_dt = to_dt.replace(hour=23, minute=59, second=59)  # End of day
                timestamp_query['$lte'] = to_dt.timestamp()
            if timestamp_query:
                query['timestamp'] = timestamp_query
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Query with sorting (newest first)
    cursor = attendance_entries_col.find(query).sort("timestamp", -1).limit(limit)
    entries = await cursor.to_list(length=limit)

    # Convert to schemas
    return [AttendanceEntryOut(**entry) for entry in entries]


@router.get("/stats", response_model=dict)
async def get_attendance_stats(
    camera_id: Optional[str] = None,
    date: Optional[str] = Query(None, description="Date to filter (YYYY-MM-DD)"),
    user=Depends(get_current_user),
):
    """
    Get attendance statistics for a day/camera.
    """
    query = {}

    if camera_id:
        query['camera_id'] = camera_id

    if date:
        try:
            date_dt = datetime.strptime(date, "%Y-%m-%d")
            next_day = date_dt + timedelta(days=1)
            query['timestamp'] = {
                '$gte': date_dt.timestamp(),
                '$lt': next_day.timestamp()
            }
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Get all entries matching query
    cursor = attendance_entries_col.find(query)
    entries = await cursor.to_list(length=1000)  # Reasonable limit

    total = len(entries)
    recognized = sum(1 for e in entries if e.get('identity_id'))
    unknown = total - recognized

    # Count by role
    role_counts = {}
    identity_counts = {}

    for entry in entries:
        identity_id = entry.get('identity_id')
        if identity_id:
            role = entry.get('identity_role')
            if role:
                role_counts[role] = role_counts.get(role, 0) + 1

            # Count unique identities
            if identity_id not in identity_counts:
                identity_counts[identity_id] = entry.get('identity_name') or identity_id

    # Time distribution (morning 6-12, afternoon 12-18, evening 18-24, night 0-6)
    time_dist = {'morning': 0, 'afternoon': 0, 'evening': 0, 'night': 0}

    for entry in entries:
        dt = datetime.fromtimestamp(entry['timestamp'])
        hour = dt.hour

        if 6 <= hour < 12:
            time_dist['morning'] += 1
        elif 12 <= hour < 18:
            time_dist['afternoon'] += 1
        elif 18 <= hour < 24:
            time_dist['evening'] += 1
        else:
            time_dist['night'] += 1

    return {
        'total_entries': total,
        'recognized_people': recognized,
        'unknown_people': unknown,
        'recognition_rate': recognized / total if total > 0 else 0,
        'unique_identities': len(identity_counts),
        'role_distribution': role_counts,
        'time_distribution': time_dist,
        'date_filter': date or "all time",
        'camera_filter': camera_id or "all cameras"
    }


@router.delete("/cleanup-old", response_model=dict)
async def cleanup_old_entries(
    days_old: int = Query(30, description="Delete entries older than N days"),
    confirm: bool = Query(False, description="Must be True to actually delete")
):
    """
    Clean up old attendance entries (keep only recent data).
    Requires confirm=True to actually delete.
    """
    if not confirm:
        return {
            'warning': 'Set confirm=True to actually delete old entries',
            'would_delete_entries_older_than_days': days_old
        }

    cutoff_time = (datetime.now() - timedelta(days=days_old)).timestamp()

    result = await attendance_entries_col.delete_many({
        'timestamp': {'$lt': cutoff_time}
    })

    return {
        'deleted_count': result.deleted_count,
        'cutoff_timestamp': cutoff_time,
        'cutoff_date': datetime.fromtimestamp(cutoff_time).isoformat()
    }