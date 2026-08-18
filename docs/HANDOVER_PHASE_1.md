# Handover — Rebuild Phase 1 Verified

1. Phase 1 created `backend_v2/`, a transitional FastAPI + PostgreSQL backend; legacy `backend/` and `frontend/` remain.
2. The production Compose stack contains only PostgreSQL and `backend_v2`; no Phase 2 domain/auth feature exists.
3. Pydantic Settings are fail-fast: required DB values and `SECRET_KEY` have no insecure fallback.
4. `CORS_ALLOWED_ORIGINS` accepts a JSON array or comma-separated value; JSON array is preferred in `.env`.
5. The local startup failure caused by plain comma-separated CORS input was reproduced and fixed.
6. Structured logging, request timing, and safe request-ID propagation are implemented.
7. Every centralized error response now carries the same request ID in its body and configured header.
8. Error handlers cover application errors, validation errors, HTTP errors, and sanitized unexpected 500 errors.
9. SQLAlchemy 2 uses an async engine/session factory with rollback and shutdown disposal.
10. PostgreSQL readiness executes a real `SELECT 1`; liveness is database-independent.
11. Alembic baseline revision is `98161483914f` (`create_initial_schema_baseline`).
12. Local Docker build passed; PostgreSQL and backend containers both reached healthy status.
13. `/health/live` and `/health/ready` both passed against the real Compose PostgreSQL service.
14. Alembic upgrade, downgrade-to-base, re-upgrade, and `current` all passed locally.
15. The first real test run found 43/45 passing and exposed two test/error-header defects.
16. Both defects were fixed; the test suite now contains 50 tests.
17. A focused artifact-environment run passed all 50 tests; see `docs/PROGRESS.md` for its logging-shim limitation.
18. `backend_v2/Dockerfile` now has a dedicated `test` target with dev-only dependencies.
19. Compose service `backend_v2_test` runs pytest, Ruff format, Ruff lint, and mypy without polluting production.
20. Run `docker compose --profile test build backend_v2_test` before Phase 2.
21. Then run `docker compose --profile test run --rm backend_v2_test`; all four gates must pass.
22. The production wheel excludes `app/tests`; the production image remains test-tool free.
23. The legacy plaintext teacher-password print is absent in this snapshot.
24. The repository owner reported rotating the exposed MongoDB database-user password; no secret is committed.
25. Read next: this file, the latest Phase 1 section in `docs/PROGRESS.md`, `backend_v2/README.md`, and Phase 2 in `docs/IMPLEMENTATION_PLAN.md`.
26. Do not repeat Phase 0 or rebuild the Phase 1 scaffold.
27. Do not rename/delete legacy `backend/` or start a frontend migration during Phase 2.
28. Phase 2 should begin with the PostgreSQL user/auth schema and secure password/token primitives.
29. Add RBAC and object-level authorization dependencies before exposing protected business routes.
30. No Git commit was created by the artifact patch.
Local Docker verification completed:
- 50 tests passed
- Ruff format check passed
- Ruff lint passed
- mypy passed for 25 source files
- 1 non-blocking StarletteDeprecationWarning remains