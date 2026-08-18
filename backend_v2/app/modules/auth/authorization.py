"""Reusable object-level authorization helpers.

Unrelated private objects are concealed as the resource's normal 404.
This avoids confirming that another teacher's or student's private
record exists while keeping role denial itself a clear 403 at the
``require_roles`` dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Collection

from app.core.exceptions import AppError
from app.modules.users.models import User


def require_own_profile(
    *,
    current_user: User,
    profile_user_id: uuid.UUID,
    not_found: Callable[[], AppError],
) -> None:
    if current_user.id != profile_user_id:
        raise not_found()


def require_related_resource(
    *,
    resource_id: uuid.UUID,
    allowed_ids: Collection[uuid.UUID],
    not_found: Callable[[], AppError],
) -> None:
    if resource_id not in allowed_ids:
        raise not_found()
