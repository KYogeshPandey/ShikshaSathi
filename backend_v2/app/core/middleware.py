"""Request correlation and request-logging middleware.

Implements the request-ID contract: every request gets a request ID
(client-supplied if present and safe, otherwise generated), the ID is
echoed back in the response header, bound into every structured log line
emitted while handling the request, and available to exception handlers
for the standard error envelope (see app/core/exceptions.py).

Design decision (recorded in docs/PROGRESS.md): request-ID propagation
and request logging are implemented as a single middleware rather than
two, since they share the same timing/context and combining them avoids
duplicating the "is this a health check" and timer bookkeeping across two
layers. The ID-selection logic is a standalone pure function
(``_extract_safe_request_id``) so it stays independently unit-testable
without needing a running app — see app/tests/test_middleware.py.
"""

from __future__ import annotations

import asyncio
import math
import re
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable

import structlog
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

_SAFE_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_HEALTH_PATHS = frozenset({"/health/live", "/health/ready"})


def _generate_request_id() -> str:
    return uuid.uuid4().hex


def _extract_safe_request_id(raw: str | None) -> str:
    """Return ``raw`` if present and safe, else a freshly generated ID.

    "Safe" means: bounded length and restricted to an
    alphanumeric/hyphen/underscore charset, so a client can't smuggle
    control characters, header-injection-style content, or an absurdly
    long value into logs or the echoed response header via this value.
    """
    if raw and _SAFE_REQUEST_ID_RE.match(raw):
        return raw
    return _generate_request_id()


class LoginAttemptLimiter:
    """Concurrency-safe fixed-window limiter keyed only by client address.

    It never reads or stores a login body, email, password, token, header,
    or cookie. Stale keys are pruned during normal checks so old callers do
    not accumulate indefinitely.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, client_key: str) -> int | None:
        """Record an attempt; return Retry-After seconds when blocked."""
        now = self._clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            attempts = self._attempts.setdefault(client_key, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                return max(1, math.ceil(attempts[0] + self.window_seconds - now))
            attempts.append(now)

            if len(self._attempts) > 10_000:
                stale_keys = [
                    key
                    for key, timestamps in self._attempts.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for key in stale_keys:
                    self._attempts.pop(key, None)
            return None


class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    """Return a standard 429 envelope after too many login attempts."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        login_path: str,
        max_attempts: int,
        window_seconds: int,
    ) -> None:
        super().__init__(app)
        self.login_path = login_path
        self.limiter = LoginAttemptLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method != "POST" or request.url.path != self.login_path:
            return await call_next(request)

        client_key = request.client.host if request.client is not None else "unknown"
        retry_after = await self.limiter.check(client_key)
        if retry_after is None:
            return await call_next(request)

        request_id = getattr(request.state, "request_id", None) or "unknown"
        request_id_header = getattr(request.state, "request_id_header", None) or "X-Request-ID"
        logger.warning(
            "login_rate_limited",
            retry_after_seconds=retry_after,
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many login attempts. Please try again later.",
                    "details": {},
                },
                "request_id": request_id,
            },
            headers={
                "Retry-After": str(retry_after),
                request_id_header: request_id,
            },
        )


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply independent fixed-window limits to configured auth POST routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        route_limits: dict[str, tuple[int, int]],
    ) -> None:
        super().__init__(app)
        self.limiters = {
            path: LoginAttemptLimiter(max_attempts=attempts, window_seconds=window)
            for path, (attempts, window) in route_limits.items()
        }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        limiter = self.limiters.get(request.url.path) if request.method == "POST" else None
        if limiter is None:
            return await call_next(request)

        client_key = request.client.host if request.client is not None else "unknown"
        retry_after = await limiter.check(client_key)
        if retry_after is None:
            return await call_next(request)

        request_id = getattr(request.state, "request_id", None) or "unknown"
        request_id_header = getattr(request.state, "request_id_header", None) or "X-Request-ID"
        message = (
            "Too many login attempts. Please try again later."
            if request.url.path.endswith("/auth/login")
            else "Too many authentication attempts. Please try again later."
        )
        logger.warning(
            "auth_rate_limited",
            path=request.url.path,
            retry_after_seconds=retry_after,
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": message,
                    "details": {},
                },
                "request_id": request_id,
            },
            headers={
                "Retry-After": str(retry_after),
                request_id_header: request_id,
            },
        )


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID to every request and logs the outcome."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = _extract_safe_request_id(request.headers.get(self.header_name))
        request.state.request_id = request_id
        request.state.request_id_header = self.header_name

        start = time.perf_counter()
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            is_health_check = request.url.path in _HEALTH_PATHS
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                logger.exception(
                    "request_failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=duration_ms,
                )
                raise

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log_method = logger.debug if is_health_check else logger.info
            log_method(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        response.headers[self.header_name] = request_id
        return response
