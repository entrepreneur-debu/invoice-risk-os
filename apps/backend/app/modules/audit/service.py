"""Tamper-evident audit trail.

`record()` appends an event in the caller's transaction, so the business change and its
audit record commit (or roll back) together. Events are numbered per organization under
a transaction-scoped advisory lock and hash-chained; `verify_chain()` recomputes it.
The table itself rejects UPDATE/DELETE via a database trigger.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models import AuditEvent
from app.models.enums import ActorType
from app.modules.context import SystemContext, TenantContext

_MAX_DETAIL_STRING = 1000


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_clean(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and len(value) > _MAX_DETAIL_STRING:
        return value[:_MAX_DETAIL_STRING] + "…"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _event_hash(fields: Mapping[str, Any]) -> str:
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _hash_fields(event: AuditEvent) -> dict[str, Any]:
    return {
        "organization_id": str(event.organization_id) if event.organization_id else None,
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.astimezone(UTC).isoformat(),
        "actor_type": event.actor_type.value,
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "details": event.details,
        "previous_hash": event.previous_hash,
    }


def record(
    db: Session,
    actor: TenantContext | SystemContext | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    details: Mapping[str, Any] | None = None,
    *,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_label: str | None = None,
    actor_type: ActorType | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> AuditEvent:
    if isinstance(actor, TenantContext):
        organization_id = actor.organization_id
        actor_user_id = actor.user_id
        actor_label = actor.user_email
        actor_type = ActorType.USER
        request_id = actor.request_id
        ip_address = actor.ip_address
    elif isinstance(actor, SystemContext):
        organization_id = actor.organization_id
        actor_label = actor.label
        actor_type = actor_type or ActorType.SYSTEM
        request_id = actor.request_id

    lock_key = str(organization_id) if organization_id else "global"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"audit:{lock_key}"})
    last = db.execute(
        select(AuditEvent.sequence, AuditEvent.hash)
        .where(
            AuditEvent.organization_id == organization_id
            if organization_id
            else AuditEvent.organization_id.is_(None)
        )
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
    ).first()

    event = AuditEvent(
        id=uuid.uuid4(),
        organization_id=organization_id,
        sequence=(last.sequence + 1) if last else 1,
        occurred_at=datetime.now(UTC),
        actor_type=actor_type or ActorType.SYSTEM,
        actor_user_id=actor_user_id,
        actor_label=actor_label,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        request_id=request_id,
        ip_address=ip_address,
        details=redact(_clean(dict(details or {}))),
        previous_hash=last.hash if last else None,
    )
    event.hash = _event_hash(_hash_fields(event))
    db.add(event)
    db.flush()
    return event


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    events_checked: int
    first_invalid_sequence: int | None = None
    reason: str | None = None


def verify_chain(db: Session, organization_id: uuid.UUID) -> ChainVerification:
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.sequence)
    )
    previous_hash: str | None = None
    expected_sequence = 1
    checked = 0
    for event in events:
        if event.sequence != expected_sequence:
            return ChainVerification(False, checked, event.sequence, "sequence_gap")
        if event.previous_hash != previous_hash:
            return ChainVerification(False, checked, event.sequence, "broken_link")
        if _event_hash(_hash_fields(event)) != event.hash:
            return ChainVerification(False, checked, event.sequence, "hash_mismatch")
        previous_hash = event.hash
        expected_sequence += 1
        checked += 1
    return ChainVerification(True, checked)


def count_events(db: Session, organization_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
        )
        or 0
    )
