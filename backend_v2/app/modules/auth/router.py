"""``/auth`` endpoints: login, refresh, logout, and the current user.

Mounted under ``API_V1_PREFIX`` via app/api/router.py, so the full paths
are e.g. ``/api/v1/auth/login``. The refresh-token cookie's ``path`` is
deliberately scoped to this router's mount path (``_auth_cookie_path``
below) so the browser only ever attaches it to these four endpoints —
not to every request to the API.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.modules.auth.dependencies import get_current_active_user, verify_same_origin
from app.modules.auth.email import OtpEmailSenderDependency
from app.modules.auth.errors import InvalidRefreshTokenError
from app.modules.auth.schemas import (
    AccessTokenInfo,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    OtpChallengeResponse,
    OtpResendRequest,
    OtpVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetEmailRequest,
    PasswordResetGrantResponse,
    PasswordResetRequestResponse,
    PasswordResetVerifyRequest,
    RefreshResponse,
)
from app.modules.auth.service import (
    AuthResult,
    AuthService,
    OtpChallengeResult,
    PasswordResetGrantResult,
    PasswordResetRequestResult,
)
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


def _otp_challenge_response(result: OtpChallengeResult) -> OtpChallengeResponse:
    return OtpChallengeResponse(
        challenge_id=result.challenge_id,
        expires_in=result.expires_in_seconds,
        resend_available_in=result.resend_available_in_seconds,
    )


def _password_reset_request_response(
    result: PasswordResetRequestResult,
) -> PasswordResetRequestResponse:
    return PasswordResetRequestResponse(
        expires_in=result.expires_in_seconds,
        resend_available_in=result.resend_available_in_seconds,
    )


def _password_reset_grant_response(
    result: PasswordResetGrantResult,
) -> PasswordResetGrantResponse:
    return PasswordResetGrantResponse(
        reset_id=result.reset_id,
        reset_token=result.reset_token,
        expires_in=result.expires_in_seconds,
    )


@router.post(
    "/login",
    response_model=LoginResponse | OtpChallengeResponse,
    summary="Authenticate with email and password",
    responses={401: {"description": "Incorrect email or password, or account deactivated."}},
)
async def login(
    payload: LoginRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_sender: OtpEmailSenderDependency,
) -> LoginResponse | OtpChallengeResponse:
    service = AuthService(session=session, settings=settings)
    if settings.LOGIN_OTP_ENABLED:
        challenge = await service.begin_otp_login(
            email=payload.email,
            password=payload.password,
            email_sender=email_sender,
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return _otp_challenge_response(challenge)
    result = await service.login(email=payload.email, password=payload.password)
    _set_refresh_cookie(response, result, settings)
    return LoginResponse(user=UserRead.model_validate(result.user), token=_token_info(result))


@router.post(
    "/otp/verify",
    response_model=LoginResponse,
    summary="Verify an email OTP and create the authenticated session",
)
async def verify_login_otp(
    payload: OtpVerifyRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LoginResponse:
    result = await AuthService(session=session, settings=settings).verify_otp(
        challenge_id=payload.challenge_id,
        otp=payload.otp,
    )
    _set_refresh_cookie(response, result, settings)
    return LoginResponse(user=UserRead.model_validate(result.user), token=_token_info(result))


@router.post(
    "/otp/resend",
    response_model=OtpChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Replace an OTP challenge after its resend cooldown",
)
async def resend_login_otp(
    payload: OtpResendRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_sender: OtpEmailSenderDependency,
) -> OtpChallengeResponse:
    result = await AuthService(session=session, settings=settings).resend_otp(
        challenge_id=payload.challenge_id,
        email_sender=email_sender,
    )
    return _otp_challenge_response(result)


@router.post(
    "/password-reset/request",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password-reset verification code",
)
async def request_password_reset(
    payload: PasswordResetEmailRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_sender: OtpEmailSenderDependency,
) -> PasswordResetRequestResponse:
    result = await AuthService(session=session, settings=settings).request_password_reset(
        email=payload.email,
        email_sender=email_sender,
    )
    return _password_reset_request_response(result)


@router.post(
    "/password-reset/resend",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resend a password-reset verification code",
)
async def resend_password_reset(
    payload: PasswordResetEmailRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    email_sender: OtpEmailSenderDependency,
) -> PasswordResetRequestResponse:
    result = await AuthService(session=session, settings=settings).resend_password_reset_otp(
        email=payload.email,
        email_sender=email_sender,
    )
    return _password_reset_request_response(result)


@router.post(
    "/password-reset/verify",
    response_model=PasswordResetGrantResponse,
    summary="Verify a password-reset code",
)
async def verify_password_reset(
    payload: PasswordResetVerifyRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PasswordResetGrantResponse:
    result = await AuthService(session=session, settings=settings).verify_password_reset_otp(
        email=payload.email,
        otp=payload.otp,
    )
    return _password_reset_grant_response(result)


@router.post(
    "/password-reset/confirm",
    response_model=PasswordResetConfirmResponse,
    summary="Set a new password using a verified reset grant",
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PasswordResetConfirmResponse:
    await AuthService(session=session, settings=settings).confirm_password_reset(
        reset_id=payload.reset_id,
        reset_token=payload.reset_token,
        new_password=payload.new_password,
    )
    return PasswordResetConfirmResponse()


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
