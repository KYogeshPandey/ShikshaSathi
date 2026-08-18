# Phase 9 handover — Deployable MVP

**Status:** COMPLETE on 2026-08-17.  
**Milestone 1:** Deployable MVP complete.  
**Milestone 2:** NOT STARTED.  
**Git operations during Phase 9:** NONE.

This is the authoritative closure record for Phase 9. It continues from the
byte-verified Phase 8 artifact and does not reopen or redesign Phases 0–8.

## 1. Outcome

The rebuilt application now has a production-shaped local deployment using
only the authoritative v2 stack:

- nginx serves the React 19 + TypeScript + Vite frontend on container port
  8080 and is the only host-published service;
- nginx proxies `/api/` and `/health/` to the internal FastAPI service;
- FastAPI runs one non-root Uvicorn worker on internal port 8000;
- PostgreSQL 16 is internal and persists through a named volume;
- a one-shot Alembic service must complete successfully before the backend can
  start;
- biometric storage uses a separate named volume; and
- the legacy Flask, MongoDB, and Create React App services are absent from
  production Compose and production images.

The single Uvicorn worker is deliberate because the login limiter is
process-local. A horizontally scaled deployment must first put a shared
limiter at the trusted ingress or replace the in-process limiter with a shared
store.

## 2. Original Critical/High closure matrix

| ID | Original finding | Rebuilt v2 mitigation | Verification evidence | Result |
|---|---|---|---|---|
| C1 | Secrets and credential-bearing debug output existed in the legacy workspace. | `backend_v2` has fail-fast environment configuration, no committed real `.env`, no secret logging, release exclusions for debug/secret artifacts, and minimal images. | Final source/clean-tree scans found zero real `.env`, private keys, debug dumps, credential output, or packaged secret/model/biometric artifacts. Candidate literals were environment placeholders, documentation placeholders, or explicitly fake test credentials. | **CLOSED for v2/source/package. HUMAN ACTION:** source cannot independently prove rotation/revocation of every historically exposed external credential. |
| C2 | Legacy JWT could fall back to an insecure signing secret. | `SECRET_KEY` is required, validated for length/quality, and has no production fallback; production debug mode is rejected. | Configuration regression tests and the full suite passed; production starts only with explicit synthetic smoke configuration. | **CLOSED** |
| C3 | The legacy Student portal had empty routes/layout and crashed. | The TypeScript frontend has guarded Student routes and working self-service profile, attendance, and announcement pages. | Phase 6/7 Student route/API tests remain in the final 40-test frontend suite; all passed. | **CLOSED** |
| C4 | Attendance access lacked reliable object-level authorization. | Teacher access is constrained by exact classroom + subject assignment; Student access uses self-only endpoints; reporting reuses the same authorization service. | Full PostgreSQL suite passed, including attendance/report scope, roster, direct-ID denial, and Student self-service regressions. | **CLOSED** |
| H1 | Authentication had no rate limiting. | Exact `POST /api/v1/auth/login` fixed-window middleware is keyed only by client address, stores no credential/body/token data, returns the standard 429 envelope and `Retry-After`, and prunes stale keys. | Three focused Phase 9 tests plus live six-attempt smoke: five validation responses followed by 429. Non-login traffic and window expiry were tested. | **CLOSED** |
| H2 | There were no meaningful automated suites. | PostgreSQL-backed backend tests, frontend Vitest tests, Ruff, mypy, compileall, builds, audits, migration tests, Compose health checks, and CI jobs now exist. | Final results are recorded in sections 8–11. | **CLOSED** |
| H3 | Face recognition was unimplemented. | Phase 5 supplies provider-neutral contracts, YuNet detection, alignment, dlib embedding, candidate-scoped matching, enrollment, audit, and recognition-attendance confirmation through `AttendanceService`. | Final suite covers contracts, providers, pipeline, matching, enrollment, UNKNOWN/AMBIGUOUS no-write behavior, FOUND/confirmation idempotency, and authorization boundaries. | **CLOSED for implementation. HUMAN ACTION:** vetted model files, representative real-data calibration, operational consent/legal review, and liveness/anti-spoofing remain required before real-world biometric use. |
| H4 | Legacy archive/photo extraction permitted unsafe paths. | ZIP members are normalized and validated before bounded streaming; `extract()`/`extractall()` are never used for application extraction; partial files are removed on failure. | Traversal, duplicate-normalized-path, size/decompression, symlink/special-entry, HTTP, storage, and reconciliation tests passed. | **CLOSED** |
| H5 | Legacy CORS allowed wildcard origins. | Production requires a non-empty explicit CORS allow-list and rejects `*`; credentialed requests retain the configured safe list. Trusted hosts are also explicit and wildcard-free in production. | Configuration tests, full suite, Compose environment, live trusted-host rejection, and source scan passed. | **CLOSED** |

Closure above means the rebuilt v2 stack replaced the vulnerable legacy
runtime. It does not claim that the retained historical Flask source was
retrofitted.

## 3. Phase 9 backend hardening

- Added validated `TRUSTED_HOSTS`, `LOGIN_RATE_LIMIT_ATTEMPTS`, and
  `LOGIN_RATE_LIMIT_WINDOW_SECONDS` settings.
- Production rejects empty/wildcard trusted-host and CORS lists, debug mode,
  and unsafe secret/database configuration.
- Added `TrustedHostMiddleware` and a concurrency-safe login limiter.
- 429 responses use the standard error envelope, request ID, and
  `Retry-After` without logging the client key or credentials.
- Existing upload, ZIP, image, recognition, report-range, CSV, and PDF bounds
  remain enforced.
- Error middleware returns controlled envelopes rather than tracebacks.
- Refresh cookies retain HttpOnly, SameSite, path, and production Secure
  handling; refresh/logout use same-origin protection.
- Logging inspection found no password, token, refresh-cookie, image,
  embedding, or private-storage-path values emitted.

## 4. Production images

### Backend

- tag: `shikshasathi-phase9-backend:latest`
- image ID: `sha256:9b8cc557040cc9cc6fc987ec34e5aa1e6eb1511cc5739688e373e5ab9c03e60c`
- size: 170,369,713 bytes
- base: Python 3.12 slim, multi-stage build
- runtime user: `appuser`, UID/GID 1000
- command: one Uvicorn worker, port 8000, proxy headers enabled, no reload
- health check: `/health/ready`
- absent from runtime: GCC, G++, CMake, pytest, Ruff, mypy, source tests
- dlib compiler/CMake requirements are confined to the builder
- key installed versions: FastAPI 0.141.1, Starlette 1.6.0,
  SQLAlchemy 2.0.52, Pydantic 2.13.4, dlib 19.24.9

### Frontend

- tag: `shikshasathi-phase9-frontend:latest`
- image ID: `sha256:1d8d2e6b35ca9017336544fa506ea15d30f33f714dc91a022b7d84c2208c4d42`
- size: 26,095,546 bytes
- build: Node 22 Alpine, `npm ci`, typecheck, Vite build
- runtime: nginx 1.28 Alpine as UID/GID 101
- absent from runtime: Node and npm
- SPA fallback is active
- `/api/` and `/health/` proxy to `backend_v2:8000`
- index/SPA HTML is no-cache; hashed assets are immutable
- CSP, frame denial, MIME-sniffing protection, referrer policy, and related
  safe headers are present

## 5. Compose and deployment procedure

`docker-compose.yml` defaults to the production-shaped stack and has no
legacy service, development bind mount, source hot reload, MongoDB, or host-
published backend/database port. Services use health/dependency conditions,
read-only filesystems where practical, `no-new-privileges`, dropped
capabilities, `init`, bounded tmpfs, appropriate restart behavior, and
project-scoped named volumes.

Deployment from an extracted release:

1. Copy `.env.example` to `.env`.
2. Replace every placeholder with deployment-specific values. Configure exact
   HTTPS frontend origins and trusted hosts; never reuse example values.
3. Terminate TLS at a trusted reverse proxy/load balancer. Keep backend and
   PostgreSQL private.
4. Run `docker compose config --quiet`.
5. Run `docker compose up --build -d`.
6. Confirm `migrate` exited 0 and `postgres`, `backend_v2`, and `frontend` are
   healthy with `docker compose ps -a`.
7. Verify `/health/live`, `/health/ready`, the frontend root, and one `/api/v1`
   request through the frontend origin.

The singleton `migrate` service runs `alembic upgrade head`. Backend startup
is blocked on its successful completion. Alembic upgrades are transactional
where PostgreSQL supports it; downgrades and destructive migrations are never
automatic. Re-running an already-current upgrade is a safe no-op.

## 6. Migration gate

- disposable PostgreSQL: 16 Alpine
- fresh upgrade: base → all seven revisions → head
- current head: `4f8c1a6e92b7`
- migration service: exited 0
- all six supported migration round-trip tests passed in the full suite
- application started and became ready against the migrated schema
- restart/persistence test retained `4f8c1a6e92b7` across PostgreSQL and
  backend restarts
- no schema migration was added or semantically changed in Phase 9
- two historical migration files received formatting-only Ruff changes

## 7. CI

`.github/workflows/ci.yml` runs on pull requests and pushes to `main`, with
least permissions and concurrency cancellation.

Jobs:

- **backend:** PostgreSQL 16 service, Python 3.12, native build prerequisites,
  dev install, Alembic upgrade/current, Ruff format/lint, scoped strict mypy,
  compileall, complete pytest suite, and pip-audit;
- **frontend:** Node 22, `npm ci`, typecheck, ESLint, complete Vitest suite,
  production build, and npm audit; and
- **images:** Compose validation plus production backend/frontend builds.

Only synthetic CI values are used. No real secret is embedded. Because Git
publication is intentionally prohibited in Phase 9, a hosted Actions run is a
post-publication human validation; equivalent local clean-source gates passed.

## 8. Backend verification

Authoritative final run, PostgreSQL 16, pytest 9.1.1,
pytest-asyncio 1.4.0:

- **718 passed**
- **0 failed**
- **0 skipped**
- **13 warnings**
- **230.80 seconds**

Warnings are nine httpx per-request-cookie deprecations, two Starlette 413
constant deprecations, one Starlette TestClient/httpx deprecation, and one
intentional duplicate-ZIP-member warning. None is a failed security or
behavior assertion.

Static gates:

- Ruff format: `216 files already formatted`
- Ruff lint: `All checks passed!`
- strict scoped mypy: success on 129 production source files
- compileall: passed
- focused Phase 9 configuration/rate-limit set: 84 passed, 3 warnings

The complete 718-test suite was not repeated after the pause because no
backend source or dependency changed after its authoritative final run.

## 9. Frontend verification

Authoritative workspace gates:

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm test -- --run`: **8 files, 40 tests passed**, 0 failed
- Vitest duration: 8.84 seconds
- `npm run build`: passed; 126 modules transformed
- `npm audit`: passed; **0 vulnerabilities**

The clean-source no-cache image independently ran:

- `npm ci`: 278 packages installed, 279 audited, 0 vulnerabilities
- typecheck: passed
- production build: passed, 126 modules transformed
- output: 0.48 kB HTML, 11.99 kB CSS, 430.21 kB JavaScript

Two Windows-host `npm ci` attempts in the temporary clean directory were
blocked by a global-cache EPERM and then npm's own `Exit handler never called`
failure. They did not reveal a source/lockfile defect. The required clean
install was therefore forced with Docker `--no-cache` and passed.

## 10. Clean-source verification

Git operations were prohibited, so the required automated equivalent used a
release-filtered copy of the authoritative workspace at:

`C:\Users\HP\.codex\visualizations\2026\08\16\01a00b2d-ecd5-7653-bfbb-0ba6cc5beecf\ShikshaSathi-phase9-clean-source`

Initial clean-copy proof:

- 408 files, 2,675,211 bytes
- zero `.git`, `node_modules`, venv/env, build/dist, cache, coverage, or log
  directories
- zero real `.env`
- zero bytecode, database, archive, model-weight, embedding, capture, or
  biometric artifacts
- required `.env.example` files retained

From that clean source:

- backend production dependencies installed and dlib compiled from source;
- backend runtime image built;
- frontend no-cache `npm ci`, typecheck, and production build passed;
- production frontend image built;
- production Compose rendered successfully;
- fresh PostgreSQL migrated to `4f8c1a6e92b7`;
- migration exited 0;
- backend/frontend/PostgreSQL were healthy;
- frontend returned 200 with the SPA root and security headers;
- `/health/live` returned 200 `alive`;
- `/health/ready` returned 200 with database `ready`; and
- `/api/v1/auth/me` reached FastAPI through nginx and returned the expected
  unauthenticated 401.

A literal fresh Git clone by someone other than the implementer remains a
post-publication human check. No browser E2E or authenticated browser smoke is
claimed; role/authorization workflows are covered by the passing suites.

## 11. Runtime smoke and persistence

The production-shaped stack passed both the initial Phase 9 smoke and the
clean-source smoke:

- frontend: 200 and healthy
- live: 200, `{"status":"alive"}`
- ready: 200, database ready
- frontend/API topology: nginx → internal FastAPI confirmed
- untrusted Host: rejected with 400
- login limit: 429 at the configured threshold
- migration: exit 0, current head
- backend shutdown/startup: clean lifecycle logs
- PostgreSQL restart: data and Alembic head persisted

The smoke used synthetic isolated credentials only. No production or user
credential was used.

## 12. Dependency and supply-chain results

Production dependency ranges were inspected. Phase 9 added no production
package. The only dependency change was the test-tool remediation:

- `pytest>=8.3,<9.0` → `pytest>=9.0.3,<10.0`
- `pytest-asyncio>=0.24,<0.25` → `pytest-asyncio>=1.4,<2.0`

Reason: pip-audit found `PYSEC-2026-1845` in pytest 8.4.2, fixed in 9.0.3.
The compatible pytest-asyncio release explicitly supports pytest 9. The full
718-test suite passed after the update.

Final pip-audit result: **no known vulnerabilities found**. The local
unpublished `shikshasathi-backend-v2` package was skipped because it is not a
PyPI distribution. Final standalone npm audit and clean no-cache npm install
both found **0 vulnerabilities**.

Python production versions are bounded ranges rather than a hash-locked
requirements file. Final image IDs and observed versions are recorded above;
future builds must continue to run tests/audits before promotion.

## 13. Secrets, privacy, and static regression scan

Final scans found:

- no real `.env`, private key, access/API token, or credible real credential;
- no debug dump, log artifact, database dump, report temporary file, model
  weight, biometric photo, embedding, or recognition capture;
- no frontend explicit `any`, TypeScript suppression, broad ESLint disable,
  local/session storage auth, duplicate transport/token store, hard-coded
  production origin, or sensitive console logging;
- exactly one centralized frontend fetch transport, including refresh;
- no backend traceback response, raw SQL concatenation from untrusted input,
  wildcard production CORS, insecure JWT fallback, or application use of ZIP
  `extract()`/`extractall()`;
- no source bind mount, reload server, legacy runtime, compiler, Node dev
  server, or secret embedded in production infrastructure.

Archive scanning is repeated against the final ZIP before external delivery.

## 14. Files added, modified, and deleted

Compared byte-for-byte with the 404-file Phase 8 archive, Phase 9 adds six
release files, modifies 45, and deletes none.

### Added (6)

- `.github/workflows/ci.yml`
- `backend_v2/app/tests/test_phase9_security.py`
- `docs/HANDOVER_PHASE_9.md`
- `frontend/.dockerignore`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

### Modified (45)

- `.env.example`
- `.gitignore`
- `API_DOCS.md`
- `README.md`
- `backend_v2/.dockerignore`
- `backend_v2/.env.example`
- `backend_v2/Dockerfile`
- `backend_v2/README.md`
- `backend_v2/pyproject.toml`
- `backend_v2/alembic/versions/20260804_1000_ca8e748dc8f2_create_biometric_enrollment_tables.py`
- `backend_v2/alembic/versions/20260809_1200_d22bce264ecd_create_biometric_embedding_and_processing_columns.py`
- `backend_v2/app/core/config.py`
- `backend_v2/app/core/middleware.py`
- `backend_v2/app/main.py`
- `backend_v2/app/modules/biometric_enrollment/models.py`
- `backend_v2/app/modules/biometric_enrollment/reconciliation.py`
- `backend_v2/app/modules/biometric_enrollment/repository.py`
- `backend_v2/app/modules/biometric_enrollment/zip_security.py`
- `backend_v2/app/modules/face_recognition/alignment.py`
- `backend_v2/app/modules/face_recognition/domain.py`
- `backend_v2/app/modules/face_recognition/providers/dlib_embedder.py`
- `backend_v2/app/modules/face_recognition/providers/yunet_detector.py`
- `backend_v2/app/tests/conftest.py`
- `backend_v2/app/tests/phase5_stage3_helpers.py`
- `backend_v2/app/tests/test_config.py`
- `backend_v2/app/tests/test_face_recognition_contracts.py`
- `backend_v2/app/tests/test_face_recognition_dlib_embedder.py`
- `backend_v2/app/tests/test_face_recognition_evaluation.py`
- `backend_v2/app/tests/test_face_recognition_health.py`
- `backend_v2/app/tests/test_face_recognition_matcher.py`
- `backend_v2/app/tests/test_face_recognition_pipeline.py`
- `backend_v2/app/tests/test_face_recognition_yunet_detector.py`
- `backend_v2/app/tests/test_phase5_stage2_bulk_zip_http.py`
- `backend_v2/app/tests/test_phase5_stage2_model_registration.py`
- `backend_v2/app/tests/test_phase5_stage2_reconciliation.py`
- `backend_v2/app/tests/test_phase5_stage3_api_http.py`
- `backend_v2/app/tests/test_phase5_stage3_match_probe_image_validation.py`
- `backend_v2/app/tests/test_phase5_stage3_model_registration.py`
- `backend_v2/app/tests/test_phase5_stage3_processing_service.py`
- `docker-compose.yml`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md`
- `frontend/.env.example`
- `frontend/README.md`

The two historical migrations and older Phase 5 production/tests listed above
received Ruff/type-only mechanical cleanup needed for the final global static
gate. No historical migration behavior or locked Phase 5 domain behavior was
redesigned. No file was deleted.

## 15. Retained legacy content

Historical Flask/MongoDB/CRA source remains for provenance and migration
reference. It is explicitly non-authoritative and is not copied into either
production image or referenced by production Compose. Root and API
documentation identify `backend_v2` plus the TypeScript/Vite frontend as the
only deployable stack.

## 16. Remaining human actions and known risks

Before a real deployment, an operator must:

1. independently confirm rotation/revocation of any historically exposed
   external credential;
2. generate unique high-entropy secrets and database credentials outside
   source control;
3. configure exact production origins/hosts and a TLS-terminating trusted
   ingress;
4. protect/backup PostgreSQL and biometric volumes and implement the approved
   retention/deletion process;
5. supply only legally vetted model artifacts with verified provenance and
   hashes;
6. calibrate thresholds on representative consented data and record FAR/FRR;
7. perform privacy/legal/consent review and add liveness/anti-spoofing before
   operational biometric attendance;
8. run the hosted GitHub Actions workflow and an independent fresh clone after
   separate Git publication; and
9. introduce a shared ingress limiter before running multiple backend workers
   or replicas.

Monitoring-platform rollout, deeper accessibility/UX work, advanced
analytics, automated biometric lifecycle, and broad performance/fuzz work are
Milestone 2 or later. Milestone 2 was not started.

## 17. Final release procedure

The cumulative artifact is created outside the authoritative workspace as
`ShikshaSathi-phase-9-complete.zip`, with exactly one root named
`ShikshaSathi-phase-9-complete/` and portable `/` entry separators.

Release verification must prove:

- no `.git`, real `.env`, dependency directory, build output, venv, cache,
  coverage, log, database, temporary report/capture, biometric artifact,
  model weight, or unrelated archive;
- zero duplicate entries and zero absolute/traversal paths;
- every ZIP file entry hashes identically to its authoritative source file;
- the archive lists/tests successfully; and
- the external final report records the ZIP's SHA-256.

The ZIP hash is deliberately reported externally rather than embedded in the
ZIP itself, which would make the archive self-referential.

Phase 9 stops here. No Milestone 2 work and no Git operation occurred.
