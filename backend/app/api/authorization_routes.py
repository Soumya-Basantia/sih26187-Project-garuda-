"""
Authorization management API routes.

Admin-only endpoints for managing authorization rules that control
who can access which zones, when, and with what objects.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.database import db
from app.auth import require_role, UserRole
from app.models.schemas import (
    AuthorizationRuleCreate,
    AuthorizationRuleUpdate,
    AuthorizationRuleOut,
    AuthorizationTestRequest,
    AuthorizationTestResult
)
from ai_engine.authorization.authorization_engine import AuthorizationEngine, PersonContext

router = APIRouter(prefix="/api/authorization", tags=["authorization"])

# Global authorization engine instance
auth_engine = AuthorizationEngine()


@router.on_event("startup")
async def load_authorization_rules():
    """Load authorization rules from database on startup"""
    from app.services.pipeline_manager import pipeline_manager
    rules = await db.authorization_rules.find().to_list(length=500)
    auth_engine.load_rules(rules)
    # Also load into pipeline manager
    pipeline_manager.auth_engine = auth_engine


@router.get("/rules", response_model=List[AuthorizationRuleOut])
async def list_authorization_rules(admin=Depends(require_role(UserRole.ADMIN))):
    """Get all authorization rules"""
    rules = await db.authorization_rules.find().to_list(length=500)
    return rules


@router.post("/rules", response_model=AuthorizationRuleOut)
async def create_authorization_rule(
    rule: AuthorizationRuleCreate,
    admin=Depends(require_role(UserRole.ADMIN))
):
    """Create new authorization rule"""
    rule_id = f"rule_{uuid.uuid4().hex[:8]}"

    doc = {
        'rule_id': rule_id,
        'name': rule.name,
        'tag_colors': rule.tag_colors,
        'allowed_zones': rule.allowed_zones,
        'forbidden_zones': rule.forbidden_zones,
        'time_restrictions': rule.time_restrictions.dict() if rule.time_restrictions else None,
        'allowed_objects': rule.allowed_objects,
        'forbidden_objects': rule.forbidden_objects,
        'priority': rule.priority,
        'override_all_rules': rule.override_all_rules,
        'escort_privileges': rule.escort_privileges,
        'requires_escort': rule.requires_escort,
        'created_by': admin['username'],
        'created_at': datetime.now(),
        'active': True
    }

    await db.authorization_rules.insert_one(doc)

    # Reload rules into engine
    await reload_rules()

    return AuthorizationRuleOut(**doc)


@router.put("/rules/{rule_id}", response_model=AuthorizationRuleOut)
async def update_authorization_rule(
    rule_id: str,
    update: AuthorizationRuleUpdate,
    admin=Depends(require_role(UserRole.ADMIN))
):
    """Update existing authorization rule"""
    existing = await db.authorization_rules.find_one({'rule_id': rule_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_dict = update.dict(exclude_unset=True)

    # Handle time_restrictions serialization
    if 'time_restrictions' in update_dict and update_dict['time_restrictions']:
        update_dict['time_restrictions'] = update_dict['time_restrictions']

    await db.authorization_rules.update_one(
        {'rule_id': rule_id},
        {'$set': update_dict}
    )

    # Reload rules into engine
    await reload_rules()

    updated = await db.authorization_rules.find_one({'rule_id': rule_id})
    return AuthorizationRuleOut(**updated)


@router.delete("/rules/{rule_id}")
async def delete_authorization_rule(
    rule_id: str,
    admin=Depends(require_role(UserRole.ADMIN))
):
    """Delete authorization rule"""
    result = await db.authorization_rules.delete_one({'rule_id': rule_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Reload rules into engine
    await reload_rules()

    return {'deleted': rule_id}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule_status(
    rule_id: str,
    admin=Depends(require_role(UserRole.ADMIN))
):
    """Enable/disable rule without deleting"""
    rule = await db.authorization_rules.find_one({'rule_id': rule_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    new_status = not rule.get('active', True)

    await db.authorization_rules.update_one(
        {'rule_id': rule_id},
        {'$set': {'active': new_status}}
    )

    # Reload rules into engine
    await reload_rules()

    return {'rule_id': rule_id, 'active': new_status}


@router.post("/test", response_model=AuthorizationTestResult)
async def test_authorization_rule(
    request: AuthorizationTestRequest,
    admin=Depends(require_role(UserRole.ADMIN))
):
    """Test authorization rules against a scenario"""
    # Parse time
    if request.current_time:
        try:
            current_time = datetime.strptime(request.current_time, "%H:%M")
            # Use today's date with the specified time
            now = datetime.now()
            current_time = current_time.replace(year=now.year, month=now.month, day=now.day)
        except:
            current_time = datetime.strptime(request.current_time, "%Y-%m-%d %H:%M")
    else:
        current_time = datetime.now()

    # Create person context
    context = PersonContext(
        tag_color=request.tag_color,
        role=auth_engine.get_role_for_tag(request.tag_color),
        zone=request.zone,
        current_time=current_time,
        objects_carried=request.objects_carried
    )

    # Check authorization
    result = auth_engine.check_authorization(context)

    return AuthorizationTestResult(
        authorized=result.authorized,
        reason=result.reason,
        matched_rule=result.matched_rule,
        violated_rule=result.violated_rule,
        severity=result.severity,
        actions_required=result.actions_required,
        can_be_escorted=result.can_be_escorted,
        escort_required=result.escort_required
    )


@router.get("/templates")
async def get_rule_templates(admin=Depends(require_role(UserRole.ADMIN))):
    """Get pre-built military rank clearance templates"""
    templates = {
        'star_5_supreme_command': {
            'name': '⭐⭐⭐⭐⭐ Level 5: Supreme Commander (War Room & Master Access)',
            'tag_colors': ['gold', 'red', 'blue'],
            'allowed_zones': ['*'],
            'forbidden_zones': [],
            'override_all_rules': True,
            'escort_privileges': True,
            'priority': 0
        },
        'star_4_division_officer': {
            'name': '⭐⭐⭐⭐ Level 4: Division Commander (Tactical Center & Perimeter HQ)',
            'tag_colors': ['blue', 'green'],
            'allowed_zones': ['tactical_ops', 'armory', 'perimeter_control', 'communications_bay', 'general_facility', 'entry_gate'],
            'forbidden_zones': ['war_room_alpha', 'command_vault'],
            'override_all_rules': False,
            'escort_privileges': True,
            'priority': 1
        },
        'star_3_field_officer': {
            'name': '⭐⭐⭐ Level 3: Field Officer / Major (Armory & Checkpoint Command)',
            'tag_colors': ['green', 'yellow'],
            'allowed_zones': ['armory', 'entry_gate', 'perimeter_control', 'duty_room', 'general_facility'],
            'forbidden_zones': ['war_room_alpha', 'command_vault', 'tactical_ops'],
            'override_all_rules': False,
            'escort_privileges': True,
            'priority': 2
        },
        'star_2_duty_officer': {
            'name': '⭐⭐ Level 2: Duty Officer / Lieutenant (Checkpoints & Quarters)',
            'tag_colors': ['green'],
            'allowed_zones': ['entry_gate', 'duty_room', 'general_facility', 'supply_depot'],
            'forbidden_zones': ['war_room_alpha', 'command_vault', 'tactical_ops', 'armory'],
            'priority': 3
        },
        'star_1_sentry_guard': {
            'name': '⭐ Level 1: Patrol Guard / Sentry (Gates & Outer Perimeter)',
            'tag_colors': ['green', 'yellow'],
            'allowed_zones': ['entry_gate', 'exit_gate', 'outer_patrol', 'watchtower'],
            'forbidden_zones': ['war_room_alpha', 'command_vault', 'tactical_ops', 'armory', 'server_room'],
            'priority': 4
        },
        'civilian_contractor': {
            'name': 'Civilian Contractor / Visitor (Escort Required)',
            'tag_colors': ['yellow'],
            'allowed_zones': ['entry_gate', 'reception', 'visitor_holding'],
            'forbidden_zones': ['*'],
            'requires_escort': True,
            'priority': 5
        }
    }
    return templates


async def reload_rules():
    """Reload rules from database into the engine and pipeline manager"""
    rules = await db.authorization_rules.find().to_list(length=500)
    auth_engine.load_rules(rules)
    try:
        from app.services.pipeline_manager import pipeline_manager
        await pipeline_manager.reload_authorization_rules()
    except Exception:
        pass
