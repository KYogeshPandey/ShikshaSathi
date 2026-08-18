"""Admin-only, read-only audit-log API.

Phase 4 Stage 3. Deliberately thin: ``AuditLogRepository`` (Stage 1,
unmodified) already has every filter/pagination shape this router needs,
and there is no scope-authorization rule beyond "caller's role is
admin" (enforced by the router's own ``require_roles`` dependency) — no
service-layer indirection is introduced just for its own sake. Exposes
only ``GET`` — no ``POST``/``PUT``/``PATCH``/``DELETE`` route exists
anywhere for this resource, matching ``AuditLogRepository``'s
structurally append-only shape (no ``update``/``delete`` method exists
to call even if a route were added by mistake).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.modules.attendance.errors import AuditLogNotFoundError
from app.modules.attendance.models import AuditOutcome
from app.modules.attendance.repository import AuditLogRepository
from app.modules.attendance.schemas import AuditLogRead
from app.modules.auth.dependencies import require_roles
from app.modules.users.models import User, UserRole
from app.schemas.pagination import Page

router = APIRouter(prefix="/audit-logs", tags=["audit logs"])

AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=Page[AuditLogRead])
async def list_audit_logs(
    _admin: AdminUser,
    session: Session,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    outcome: AuditOutcome | None = None,
    entity_type: str | None = None,
    classroom_id: uuid.UUID | None = None,
    subject_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AuditLogRead]:
    """Deterministically ordered (newest first), bounded, filtered audit-log list.

    Admin-only — a teacher or student caller receives 403 from the
    ``require_roles`` dependency before this function body ever runs.
    """
    repository = AuditLogRepository(session)
    rows = await repository.list(
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        entity_type=entity_type,
        classroom_id=classroom_id,
        subject_id=subject_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    total = await repository.count(
        actor_user_id=actor_user_id,
        action=action,
        outcome=outcome,
        entity_type=entity_type,
        classroom_id=classroom_id,
        subject_id=subject_id,
        date_from=date_from,
        date_to=date_to,
    )
    return Page[AuditLogRead](
        items=[AuditLogRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{audit_log_id}", response_model=AuditLogRead)
async def get_audit_log(
    audit_log_id: uuid.UUID, _admin: AdminUser, session: Session
) -> AuditLogRead:
    row = await AuditLogRepository(session).get_by_id(audit_log_id)
    if row is None:
        raise AuditLogNotFoundError()
    return AuditLogRead.model_validate(row)
