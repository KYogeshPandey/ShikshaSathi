"""FastAPI application factory and ASGI entrypoint.

Run with: ``uvicorn app.main:app --host 0.0.0.0 --port 8000``
(see backend_v2/README.md for the full command set).

Phase 1 built the application skeleton. Phase 2 added authentication and
RBAC. Phase 3 adds authenticated academic/profile/announcement management,
role-scoped reads, and bounded bulk imports under ``/api/v1``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import get_settings
from app.core.exceptions import EXCEPTION_HANDLERS
from app.core.logging import configure_logging
from app.core.middleware import AuthRateLimitMiddleware, RequestIDMiddleware
from app.db.session import dispose_all_engines
from app.schemas.health import RootResponse

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "startup",
        app_name=settings.APP_NAME,
        app_env=settings.APP_ENV.value,
        app_version=settings.APP_VERSION,
    )
    try:
        yield
    finally:
        await dispose_all_engines()
        logger.info("shutdown", app_name=settings.APP_NAME)


def create_app() -> FastAPI:
    """Build a fully configured FastAPI application.

    Fails loudly (via ``get_settings()`` -> ``Settings()``) if required
    configuration is missing or invalid — see app/core/config.py. There
    is no destructive database operation anywhere in this function or in
    ``lifespan`` above; the database is only ever read via a lightweight
    ``SELECT 1`` in GET /health/ready.
    """
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        description=(
            "ShikshaSathi v2 deployable MVP backend: authentication, "
            "role-scoped academic management, attendance, biometric "
            "recognition workflows, reports, and bounded exports."
        ),
    )

    # Starlette adds middleware inside-out. Request IDs remain the outermost
    # boundary, then CORS; host and login-limit rejections therefore keep
    # correlation and allowed-origin response headers.
    auth_prefix = f"{settings.API_V1_PREFIX}/auth"
    app.add_middleware(
        AuthRateLimitMiddleware,
        route_limits={
            f"{auth_prefix}/login": (
                settings.LOGIN_RATE_LIMIT_ATTEMPTS,
                settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
            ),
            f"{auth_prefix}/otp/verify": (
                settings.OTP_VERIFY_RATE_LIMIT_ATTEMPTS,
                settings.OTP_VERIFY_RATE_LIMIT_WINDOW_SECONDS,
            ),
            f"{auth_prefix}/otp/resend": (
                settings.OTP_RESEND_RATE_LIMIT_ATTEMPTS,
                settings.OTP_RESEND_RATE_LIMIT_WINDOW_SECONDS,
            ),
        },
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.TRUSTED_HOSTS,
        www_redirect=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware, header_name=settings.REQUEST_ID_HEADER)

    for exc_class, handler in EXCEPTION_HANDLERS.items():
        app.add_exception_handler(exc_class, handler)

    # Health checks are deliberately unversioned (mounted directly on the
    # app); business routers attach under API_V1_PREFIX via api_router
    # (see app/api/router.py).
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", response_model=RootResponse, tags=["root"], summary="Service info")
    async def root() -> RootResponse:
        return RootResponse(
            name=settings.APP_NAME,
            version=settings.APP_VERSION,
            docs="/docs",
            health={"live": "/health/live", "ready": "/health/ready"},
        )

    return app


app = create_app()
