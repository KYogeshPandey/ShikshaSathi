"""Reusable FastAPI authentication and RBAC dependencies.

- ``get_current_user`` — decodes the ``Authorization: Bearer`` access
  token and loads the corresponding user from PostgreSQL. Raises 401
  for anything wrong with the token itself, or if the token's subject
  no longer resolves to a real user.
- ``get_current_active_user`` — the above, plus a 401 if the account
  has been deactivated. This is the dependency almost every future
  protected route should use.
- ``require_roles(*roles)`` — builds a dependency that further requires
  the current active user's *database* role (never a token claim — see
  app/modules/auth/security.py's ``create_access_token``) to be one of
  ``roles``, else 403. Reusable by any future admin/teacher/student
  router (instruction F).
- ``verify_same_origin`` — a lightweight CSRF mitigation for the two
  cookie-authenticated, state-changing endpoints (``/auth/refresh``,
  ``/auth/logout`` — see app/modules/auth/router.py and
  docs/adr/0006-identity-and-auth-foundations.md for the full
  rationale alongside the SameSite=Lax cookie attribute).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.auth.security import TokenError, decode_access_token
from app.modules.users.models import User, UserRole
from app.modules.users.repository import UserRepository

logger = structlog.get_logger(__name__)

# auto_error=False: a missing Authorization header should raise our own
# AuthenticationError (401, standard envelope) rather than FastAPI
# HTTPBearer's default plain-text 403.
_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(HTTPException):
    """A 401 with a ``WWW-Authenticate`` header, per the Bearer-token convention."""

    def __init__(self, detail: str = "Could not validate credentials.") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """Resolve the caller's ``User`` row from a Bearer access token.

    Every failure — no header, malformed token, expired token, wrong
    signature, wrong audience/issuer, wrong token type, or a subject
    that no longer exists — raises the same ``AuthenticationError``
    (401). The underlying PyJWT exception is never surfaced (see
    app/modules/auth/security.py's ``TokenError``).
    """
    if credentials is None:
        raise AuthenticationError("Not authenticated.")

    try:
        payload = decode_access_token(credentials.credentials, settings=settings)
    except TokenError as exc:
        raise AuthenticationError() from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError() from exc

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        # A structurally valid, correctly-signed token whose subject
        # has since been deleted. Rejected exactly like any other
        # invalid token (instruction C: "A valid token belonging to a
        # missing or inactive user must be rejected.").
        raise AuthenticationError()
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """``get_current_user``, plus rejecting a deactivated account.

    Reads ``is_active`` fresh on every request (it is an attribute of
    the ``User`` row just loaded from the database above) — an admin
    deactivating a user takes effect on this user's very next request,
    not whenever their current access token happens to expire
    (instruction A/F).
    """
    if not current_user.is_active:
        raise AuthenticationError("This account has been deactivated.")
    return current_user


def require_roles(
    *allowed_roles: UserRole,
) -> Callable[[User], Awaitable[User]]:
    """Build a dependency requiring the caller's DB role to be one of ``allowed_roles``.

    Example (a future Phase 3 router)::

        @router.get("/admin/reports")
        async def reports(
            _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
        ) -> ...: ...

    Unauthenticated -> 401 (from ``get_current_active_user``).
    Authenticated but wrong role -> 403.
    """

    async def _dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _dependency


async def verify_same_origin(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """Reject a cross-origin request to a cookie-authenticated endpoint.

    The primary CSRF defense is the refresh-token cookie's
    ``SameSite=Lax`` attribute (app/modules/auth/router.py), which
    already stops browsers from attaching the cookie to a cross-site
    POST. This dependency is a second, independent layer for browsers
    or proxies that do not enforce SameSite: if the request carries an
    ``Origin`` header (which real cross-origin ``fetch``/XHR requests
    always do) that is not in ``CORS_ALLOWED_ORIGINS``, the request is
    rejected outright. A request with no ``Origin`` header at all is
    allowed through — same-origin requests do not always send one, and
    the SameSite cookie attribute is what actually gates those.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin not in settings.CORS_ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin request rejected.",
        )
