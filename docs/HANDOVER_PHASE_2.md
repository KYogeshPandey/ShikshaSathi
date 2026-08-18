# Handover — Rebuild Phase 2 Complete and Locally Verified

1. Phase 2 implements PostgreSQL-backed users, authentication, refresh-token sessions, and role-based access control.
2. Migration head is `6eeb9420bf8b`; its parent is Phase 1 revision `98161483914f`.
3. Tables added: `users` and `refresh_sessions`; PostgreSQL enum: `user_role`.
4. Endpoints added: `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, and `GET /api/v1/auth/me`.
5. User roles are exactly `admin`, `teacher`, and `student`.
6. Passwords use Argon2id; plaintext passwords and password hashes are never returned or logged.
7. Access tokens are signed JWTs containing issuer, audience, expiry, subject, token type, issued-at time, and JTI.
8. Access tokens intentionally carry no trusted role claim; protected requests reload the user and current role from PostgreSQL.
9. Inactive or deleted users are rejected even when an otherwise valid access token exists.
10. Refresh tokens are opaque random values; only SHA-256 digests are stored in PostgreSQL.
11. Refresh-token rotation records replacement lineage and invalidates the previously used token.
12. Reuse of a rotated token is detected and revokes all active refresh sessions for the affected user.
13. Refresh-token lookup uses `SELECT ... FOR UPDATE`, making rotation atomic under concurrent requests.
14. Logout revokes the relevant server-side refresh session and clears the refresh cookie.
15. Refresh cookies are HttpOnly, path-scoped, SameSite-configured, and Secure in production.
16. Origin allow-list checks protect cookie-authenticated refresh and logout requests.
17. `UserRole` persists lowercase enum values matching migration `6eeb9420bf8b`.
18. Invalid SQLAlchemy dataclass-only `repr` column options were removed.
19. Explicit model `__repr__` methods exclude password hashes and refresh-token hashes.
20. `app/db/models.py` centrally registers `User` and `RefreshSession` with Alembic metadata.
21. Database-backed HTTP tests use `httpx.AsyncClient` with `ASGITransport`.
22. This keeps FastAPI, asyncpg, and the test `AsyncSession` on the same event loop.
23. The Docker test profile starts an isolated PostgreSQL test service and applies Alembic migrations before pytest.
24. Local authoritative Docker gate completed successfully.
25. Pytest result: **144 tests passed**.
26. Ruff format result: **60 files already formatted**.
27. Ruff lint result: **All checks passed**.
28. mypy result: **no issues found in 54 source files**.
29. PostgreSQL test service reached healthy status and Alembic upgraded through `98161483914f` to `6eeb9420bf8b`.
30. Ten non-blocking deprecation warnings remain: one Starlette/TestClient warning and nine HTTPX per-request-cookie warnings.
31. Phase 2 blockers: none.
32. Do not add new authentication architecture in Phase 3; reuse the current user, RBAC, token, cookie, and session foundations.
33. Phase 3 starts with academic domain models and management APIs for classrooms, subjects, teachers, students, timetable, and announcements.
34. Before future deployment, rerun the Docker gate and verify `/health/live` and `/health/ready` in the target environment.