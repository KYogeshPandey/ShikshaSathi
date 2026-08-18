"""``/auth`` endpoints: login, refresh, logout, and the current user.

Mounted under ``API_V1_PREFIX`` via app/api/router.py, so the full paths
are e.g. ``/api/v1/auth/login``. The refresh-token cookie's ``path`` is
deliberately scoped to this router's mount path (``_auth_cookie_path``
below) so the browser only ever attaches it to these four endpoints —
not to every request to the API.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user, verify_same_origin
from app.modules.auth.errors import InvalidRefreshTokenError
from app.modules.auth.schemas import (
    AccessTokenInfo,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    RefreshResponse,
)
from app.modules.auth.service import AuthResult, AuthService
from app.modules.users.models import User
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_cookie_path(settings: Settings) -> str:
    return f"{settings.API_V1_PREFIX}/auth"


def _set_refresh_cookie(response: Response, result: AuthResult, settings: Settings) -> None:
    response.set_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        value=result.refresh_token,
        max_age=result.refresh_expires_in_seconds,
        httponly=True,
        secure=settings.REFRESH_TOKEN_COOKIE_SECURE,
        samesite=settings.REFRESH_TOKEN_COOKIE_SAMESITE,
        path=_auth_cookie_path(settings),
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.REFRESH_TOKEN_COOKIE_NAME,
        path=_auth_cookie_path(settings),
        domain=settings.REFRESH_TOKEN_COOKIE_DOMAIN,
    )


def _token_info(result: AuthResult) -> AccessTokenInfo:
    return AccessTokenInfo(
        access_token=result.access_token,
        expires_in=result.access_expires_in_seconds,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate with email and password",
    responses={401: {"description": "Incorrect email or password, or account deactivated."}},
)
async def login(
    payload: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    service = AuthService(session=session, settings=settings)
    result = await service.login(email=payload.email, password=payload.password)
    _set_refresh_cookie(response, result, settings)
    return LoginResponse(user=UserRead.model_validate(result.user), token=_token_info(result))


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Exchange the refresh-token cookie for a new access token",
    responses={401: {"description": "Refresh session is invalid, expired, or reused."}},
)
async def refresh(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _origin_ok: Annotated[None, Depends(verify_same_origin)],
) -> RefreshResponse:
    raw_refresh_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    if not raw_refresh_token:
        raise InvalidRefreshTokenError()

    service = AuthService(session=session, settings=settings)
    result = await service.refresh(raw_refresh_token=raw_refresh_token)
    _set_refresh_cookie(response, result, settings)
    return RefreshResponse(token=_token_info(result))


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Revoke the current refresh session and clear its cookie",
)
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _origin_ok: Annotated[None, Depends(verify_same_origin)],
) -> LogoutResponse:
    raw_refresh_token = request.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    service = AuthService(session=session, settings=settings)
    # Idempotent (see AuthService.logout's docstring) — repeated or
    # missing-cookie calls are not errors.
    await service.logout(raw_refresh_token=raw_refresh_token)
    _clear_refresh_cookie(response, settings)
    return LogoutResponse()


@router.get(
    "/me",
    response_model=UserRead,
    summary="The currently authenticated user",
    responses={401: {"description": "Missing, invalid, or expired access token."}},
)
async def me(current_user: Annotated[User, Depends(get_current_active_user)]) -> UserRead:
    return UserRead.model_validate(current_user)
