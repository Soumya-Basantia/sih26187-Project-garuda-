"""
AuthorizationEngine — Flexible rule-based access control system.

This module handles authorization decisions based on:
- Color tag detection (Student/Teacher/Staff/Visitor)
- Zone-based access control
- Time restrictions
- Object carrying restrictions
- Escort privileges

Every authorization decision is explainable and logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional, List, Dict, Any

logger = logging.getLogger("garude.authorization")


@dataclass
class AuthorizationRule:
    """Represents a single authorization rule"""
    rule_id: str
    name: str
    tag_colors: List[str]
    allowed_zones: List[str]
    forbidden_zones: List[str]
    time_restrictions: Optional[Dict] = None
    allowed_objects: List[str] = field(default_factory=list)
    forbidden_objects: List[str] = field(default_factory=list)
    priority: int = 1
    override_all_rules: bool = False
    escort_privileges: bool = False
    requires_escort: bool = False
    active: bool = True
    created_by: str = "system"
    created_at: float = 0.0


@dataclass
class PersonContext:
    """Context information about a person for authorization checking"""
    tag_color: str
    role: str  # Derived from tag color
    zone: str
    current_time: datetime
    objects_carried: List[str] = field(default_factory=list)
    track_id: int = 0
    has_escort: bool = False
    escorted_by: Optional[str] = None


@dataclass
class AuthorizationResult:
    """Result of an authorization check"""
    authorized: bool
    reason: str
    matched_rule: Optional[str] = None
    violated_rule: Optional[str] = None
    severity: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    actions_required: List[str] = field(default_factory=list)
    can_be_escorted: bool = False
    escort_required: bool = False
    confidence: float = 1.0


class AuthorizationEngine:
    """
    Rule-based authorization engine with priority handling.

    Rules are evaluated in priority order (0 = highest).
    Master access rules (override_all_rules=True) take precedence.
    """

    # Tag color to role mapping
    TAG_ROLE_MAP = {
        'red': 'student',
        'blue': 'teacher',
        'green': 'staff',
        'yellow': 'visitor',
        'unknown': 'unknown'
    }

    def __init__(self):
        self.rules: List[AuthorizationRule] = []
        logger.info("AuthorizationEngine initialized")

    def load_rules(self, rules_from_db: List[Dict]):
        """Load rules from database, sorted by priority"""
        self.rules = []
        for rule_doc in rules_from_db:
            rule = AuthorizationRule(
                rule_id=rule_doc['rule_id'],
                name=rule_doc['name'],
                tag_colors=rule_doc['tag_colors'],
                allowed_zones=rule_doc.get('allowed_zones', []),
                forbidden_zones=rule_doc.get('forbidden_zones', []),
                time_restrictions=rule_doc.get('time_restrictions'),
                allowed_objects=rule_doc.get('allowed_objects', []),
                forbidden_objects=rule_doc.get('forbidden_objects', []),
                priority=rule_doc.get('priority', 1),
                override_all_rules=rule_doc.get('override_all_rules', False),
                escort_privileges=rule_doc.get('escort_privileges', False),
                requires_escort=rule_doc.get('requires_escort', False),
                active=rule_doc.get('active', True),
                created_by=rule_doc.get('created_by', 'system'),
                created_at=rule_doc.get('created_at', 0.0)
            )
            self.rules.append(rule)

        # Sort by priority (lower number = higher priority)
        self.rules.sort(key=lambda r: r.priority)
        logger.info(f"Loaded {len(self.rules)} authorization rules")

    def check_authorization(self, context: PersonContext) -> AuthorizationResult:
        """
        Check if a person is authorized for their current context.

        Args:
            context: PersonContext with tag color, zone, time, objects, etc.

        Returns:
            AuthorizationResult with authorized status and details
        """
        # Find applicable rules for this person's tag color
        applicable_rules = [
            r for r in self.rules
            if r.active and context.tag_color in r.tag_colors
        ]

        if not applicable_rules:
            return AuthorizationResult(
                authorized=False,
                reason=f"no_rules_for_tag_{context.tag_color}",
                severity="MEDIUM",
                actions_required=["verify_identity", "manual_check"]
            )

        # Check if being escorted
        if context.has_escort:
            return AuthorizationResult(
                authorized=True,
                reason="escorted_by_authorized_person",
                matched_rule="escort_privilege",
                severity="LOW",
                can_be_escorted=True
            )

        # Apply rules in priority order
        for rule in applicable_rules:
            result = self._evaluate_rule(rule, context)
            if result is not None:
                return result

        # No rule explicitly allowed this
        return AuthorizationResult(
            authorized=False,
            reason="not_explicitly_authorized",
            severity="MEDIUM",
            actions_required=["verify_identity", "check_authorization"]
        )

    def _evaluate_rule(self, rule: AuthorizationRule, context: PersonContext) -> Optional[AuthorizationResult]:
        """Evaluate a single rule against the context"""

        # Master override check
        if rule.override_all_rules:
            return AuthorizationResult(
                authorized=True,
                reason="master_access_override",
                matched_rule=rule.name,
                can_be_escorted=rule.escort_privileges,
                severity="LOW"
            )

        # Forbidden zone check (takes precedence)
        if context.zone in rule.forbidden_zones:
            return AuthorizationResult(
                authorized=False,
                reason="zone_forbidden",
                violated_rule=rule.name,
                severity="HIGH",
                actions_required=["immediate_alert", "security_dispatch"]
            )

        # Allowed zone check
        zone_allowed = (
            '*' in rule.allowed_zones or
            context.zone in rule.allowed_zones or
            'all' in rule.allowed_zones
        )

        if not zone_allowed:
            return None  # Try next rule

        # Time restriction check
        if rule.time_restrictions:
            if not self._check_time_authorization(context.current_time, rule.time_restrictions):
                return AuthorizationResult(
                    authorized=False,
                    reason="outside_authorized_hours",
                    violated_rule=rule.name,
                    severity="MEDIUM",
                    actions_required=["check_schedule", "verify_purpose"]
                )

        # Object restriction check
        forbidden_objects = rule.forbidden_objects
        carried_forbidden = [obj for obj in context.objects_carried
                            if any(fob in obj for fob in forbidden_objects)]

        if carried_forbidden:
            return AuthorizationResult(
                authorized=False,
                reason="forbidden_objects_detected",
                violated_rule=rule.name,
                severity="HIGH",
                actions_required=["security_check", "object_inspection"],
                confidence=0.9
            )

        # Escort requirement check
        if rule.requires_escort and not context.has_escort:
            return AuthorizationResult(
                authorized=False,
                reason="escort_required",
                violated_rule=rule.name,
                severity="MEDIUM",
                escort_required=True,
                actions_required=["assign_escort", "verify_purpose"]
            )

        # All checks passed
        return AuthorizationResult(
            authorized=True,
            reason="rule_match_authorized",
            matched_rule=rule.name,
            can_be_escorted=rule.escort_privileges,
            severity="LOW"
        )

    def _check_time_authorization(self, current_time: datetime, time_restrictions: Dict) -> bool:
        """Check if current time falls within authorized hours"""
        current_hour = current_time.hour
        current_minute = current_time.minute
        weekday = current_time.weekday()  # 0=Monday, 6=Sunday

        # Check all_days restriction
        if 'all_days' in time_restrictions:
            return self._is_time_in_range(
                current_hour, current_minute,
                time_restrictions['all_days']
            )

        # Check weekday/weekend restrictions
        is_weekend = weekday >= 5  # Saturday or Sunday

        if is_weekend and 'weekends' in time_restrictions:
            return self._is_time_in_range(
                current_hour, current_minute,
                time_restrictions['weekends']
            )
        elif not is_weekend and 'weekdays' in time_restrictions:
            return self._is_time_in_range(
                current_hour, current_minute,
                time_restrictions['weekdays']
            )

        # Check special dates
        date_str = current_time.strftime('%Y-%m-%d')
        if 'special_dates' in time_restrictions and date_str in time_restrictions['special_dates']:
            return self._is_time_in_range(
                current_hour, current_minute,
                time_restrictions['special_dates'][date_str]
            )

        # No time restriction matches
        return True

    def _is_time_in_range(self, hour: int, minute: int, time_range: Dict) -> bool:
        """Check if time is within the given range"""
        try:
            start = time_range.get('start', '00:00')
            end = time_range.get('end', '23:59')

            start_h, start_m = map(int, start.split(':'))
            end_h, end_m = map(int, end.split(':'))

            current_minutes = hour * 60 + minute
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            # Handle overnight ranges (e.g., 22:00 to 06:00)
            if end_minutes < start_minutes:
                return current_minutes >= start_minutes or current_minutes <= end_minutes
            else:
                return start_minutes <= current_minutes <= end_minutes
        except Exception as e:
            logger.error(f"Error parsing time range: {e}")
            return True  # Default to allowed if parsing fails

    def get_role_for_tag(self, tag_color: str) -> str:
        """Get role name for a tag color"""
        return self.TAG_ROLE_MAP.get(tag_color.lower(), 'unknown')

    def check_escort_permission(self, escort_context: PersonContext) -> bool:
        """Check if a person can escort others"""
        result = self.check_authorization(escort_context)
        return result.can_be_escorted and result.authorized

    def get_rules_for_tag(self, tag_color: str) -> List[AuthorizationRule]:
        """Get all active rules applicable to a tag color"""
        return [
            r for r in self.rules
            if r.active and tag_color in r.tag_colors
        ]

    def add_rule(self, rule: AuthorizationRule):
        """Add a new rule and re-sort"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
        logger.info(f"Added rule: {rule.name} (priority {rule.priority})")

    def remove_rule(self, rule_id: str):
        """Remove a rule by ID"""
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
        logger.info(f"Removed rule: {rule_id}")

    def get_rule_by_id(self, rule_id: str) -> Optional[AuthorizationRule]:
        """Get a rule by its ID"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None
