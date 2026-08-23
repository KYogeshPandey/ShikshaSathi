# ShikshaSathi v2 — Current Architecture

This document began as the Phase 0 target architecture. Phases 1–9 have now
implemented the Deployable MVP described here. Historical rationale remains
preserved, while §12–§14 record the final production and legacy-retirement
boundaries. Finding references such as `(AUDIT §x.x)` point to the original
legacy defect that motivated the v2 design.

Style: **modular monolith**. One deployable backend service, one deployable frontend, clear internal module boundaries. No microservices, no Kubernetes (explicitly out of scope per the rebuild brief).

---

## 1. Stack

**Backend**
- Python 3.12+
- FastAPI (replaces Flask)
- Pydantic v2 (already partially used in the legacy app's `schemas/` — extended to cover every request/response)
- SQLAlchemy 2 (replaces raw pymongo dict access)
- Alembic (replaces the ad hoc `debug_db.py`/`fix_db.py` scripts — AUDIT §1.4, §3.2 — with real, versioned migrations)
- PostgreSQL (replaces MongoDB)
- pytest (replaces the currently-empty test suite — AUDIT §2.12)
- Ruff (lint), mypy (type-check)

**Frontend**
- React + TypeScript (replaces untyped JS)
- Vite (replaces `react-scripts`/CRA — also brings the frontend in line with what `README.md` already claimed, AUDIT §4.1)
- Tailwind CSS (reused directly — AUDIT: "Reuse" in migration map)
- React Router
- TanStack Query (replaces manual axios calls with no caching/retry/401-handling — AUDIT §3.4)
- React Hook Form + Zod (form state + schema validation, shared validation shapes with backend Pydantic models where practical)
- Vitest + React Testing Library (there are currently zero frontend tests)
- Playwright — later, once there's enough surface area for meaningful e2e coverage

**Infrastructure**
- Docker + Docker Compose for local/dev (no Dockerfile exists today — AUDIT §4.4)
- PostgreSQL as a Compose service
- GitHub Actions CI for migrations, tests, static checks, dependency audits,
  frontend build, and production image builds (Phase 9 closure of AUDIT §4.5)

---

## 2. Repository layout

```
ShikshaSathi/
├── backend_v2/
│   ├── app/
│   │   ├── main.py                # FastAPI app instantiation
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic Settings — single source of env config
│   │   │   ├── security.py        # JWT issue/verify, password hashing
│   │   │   └── logging.py         # structured logging setup
│   │   ├── db/
│   │   │   ├── session.py         # SQLAlchemy engine/session
│   │   │   └── base.py
│   │   ├── modules/
│   │   │   ├── auth/               # login, tokens, refresh
│   │   │   ├── users/              # admin/teacher/student accounts
│   │   │   ├── academics/          # classrooms, subjects, timetable
│   │   │   ├── attendance/         # attendance core + audit trail
│   │   │   ├── announcements/
│   │   │   ├── reports/
│   │   │   └── face_recognition/   # detector/embedder/matcher boundary (AUDIT §2.13)
│   │   ├── api/                   # versioned routers, thin — delegate to modules/
│   │   └── tests/
│   ├── alembic/
│   ├── .env.example
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/                   # routing, providers
│   │   ├── features/              # one folder per domain (mirrors backend modules/)
│   │   ├── api/                   # typed API client, TanStack Query hooks
│   │   ├── components/            # shared/reusable UI
│   │   └── test/
│   ├── vite.config.ts
│   └── package.json
├── docker-compose.yml
├── docs/
└── shared/                        # (currently empty in legacy repo — reserved for shared types/contracts if adopted later)
```

Each backend `modules/<name>/` follows the same internal shape: `router.py`, `service.py`, `repository.py`, `schemas.py`, `models.py`. This is a direct, deliberate improvement on the legacy layout, where routes/services/models were three separate top-level folders (`api/v1/`, `services/`, `models/`) with no per-feature grouping — which is part of why it was possible for `services/timetable_service.py` and `services/announcement_service.py` to go empty and dead without anyone noticing (AUDIT: Legacy Migration Map, Timetable/Announcements rows). Co-locating a feature's router/service/repository/schema makes dead code far more visible.

---

## 3. Request lifecycle

```
Client (React) → TanStack Query → typed API client
   → FastAPI router (thin: parse path/query, call service)
   → service (business logic, orchestrates repositories)
   → repository (SQLAlchemy queries, one repository per aggregate)
   → PostgreSQL
```

Errors bubble up as typed exceptions (see §7) and are translated to a consistent JSON error shape at the router/middleware boundary — never as raw `str(exception)` returned to the client, which was a real issue in the legacy decorators (AUDIT §2.4, Medium finding).

---

## 4. Authentication boundary

- `core/security.py` owns token issuance/verification exclusively. No route or service calls a JWT library directly — this consolidates what used to be split across `utils/auth.py`'s two overlapping decorators (AUDIT §2.4).
- Access + refresh token pair (legacy had access-token-only, no revocation path — AUDIT §2.3).
- `JWT_SECRET` (renamed/kept as-is, TBD in Phase 2) has **no fallback default** — startup fails loudly if unset. This directly closes Critical finding C2.
- Rate limiting on `/auth/login` and other write-heavy endpoints from day one (legacy declared `flask-limiter` as a dependency but never used it — AUDIT §2.6, High H1).

## 5. Authorization and ownership checks

- Role check (`admin`/`teacher`/`student`) stays as a first gate, same concept as legacy `requires_roles`.
- **New:** an explicit ownership-check layer in the service tier for every teacher-scoped resource (classroom, subject, student roster, attendance record) — verifying the authenticated user is actually assigned to the resource before allowing read or write. This is the direct fix for Critical finding C4 (any teacher could read/write any classroom's attendance in the legacy app). Ownership checks are implemented once, as a reusable dependency, not copy-pasted per route.
- Student-role access remains identity-derived (`current_user.id`), matching the one place the legacy app got this right (`/attendance/mystats` — AUDIT §2.4 positive note).

## 6. Database access pattern & transaction handling

- Repository-per-aggregate over raw SQLAlchemy sessions; no direct ORM queries inside routers.
- Explicit transaction boundaries at the service layer (`async with session.begin():` style), replacing MongoDB's implicit single-document-write semantics — attendance bulk-save in particular (legacy `save_bulk_attendance`) needs a real transaction so a partial failure can't leave a batch half-written.
- Startup fails fast if the database is unreachable — no silent `_db = None` fallback (AUDIT §2.2).

## 7. Validation & error format

- Every request/response has a Pydantic v2 model; FastAPI generates OpenAPI from them automatically (also solves AUDIT §4.2 — API docs going stale, since they'd be generated rather than hand-maintained).
- Standard error envelope, e.g. `{"success": false, "error": {"code": "...", "message": "..."}}`, produced by a single exception-handling middleware — not ad hoc `try/except` blocks per route (legacy pattern, AUDIT §2.7).

## 8. Logging & audit trail

- Structured logging (`core/logging.py`) replaces every `print()` call in the legacy backend (AUDIT §2.7). No secret values are ever logged — a direct, permanent fix for how the MongoDB URI leak happened in the first place (AUDIT §1.4/C1).
- The existing audit-log feature concept (legacy `audit_log_service.py`/`AuditLogPage.jsx`) is kept and extended to also record authorization failures (blocked attempts), not just successful admin actions — see Phase 4.

## 9. Face-recognition boundary

- Kept as an isolated module (`modules/face_recognition/`) behind a narrow interface: `detect(image) -> [face]`, `embed(face) -> vector`, `match(vector, candidates) -> student_id | None` — the same three-stage shape the legacy `ml/` folder already implied by its file names, just actually implemented this time (AUDIT §2.13/H3).
- **Provider decided (Rebuild Phase 5 Stage 1):** server-side local Python inference, per `docs/adr/0005-face-recognition-provider-pending.md` (now `Accepted`) — no browser-side or hosted-API inference for the MVP. The module boundary above is still what makes the provider swappable later; Stage 1 gave that boundary concrete typed `Protocol` interfaces (`app/modules/face_recognition/protocols.py`) and value objects (`domain.py`), with no provider-specific type (OpenCV, dlib, or otherwise) crossing it.
- **Detector/embedder/matcher implemented (Rebuild Phase 5 Stage 3):** real face detection (YuNet via OpenCV's `cv2.FaceDetectorYN`), a standalone landmark-driven alignment/normalization stage, real embedding (dlib's `dlib_face_recognition_resnet_model_v1`, 128-D, L2-normalized), and a candidate-scoped cosine-similarity matcher — see `docs/adr/0011-phase5-stage3-embedding-model-and-matching.md` and `docs/HANDOVER_PHASE_5_STAGE_3.md` for the full design. `FaceMatcher.match` takes an explicit, caller-supplied candidate list (never queries a repository itself) — the concrete mechanism behind "matching is always scoped, never institution-wide."
- Biometric images/embeddings are treated as sensitive data: stored outside the web root (`Settings.BIOMETRIC_STORAGE_ROOT`), referenced by ID, never returned in bulk API responses, and covered by their own retention/deletion policy — defined in `docs/BIOMETRIC_DATA_POLICY.md` (Rebuild Phase 5 Stage 1; undefined before this, since the legacy app had no working implementation to have a policy about). Stage 3 extends this: the computed embedding (a new `biometric_embeddings` table, migration `d22bce264ecd`, parent `ca8e748dc8f2`) is itself never returned by any API response and never appears in audit-log metadata.
- **Enrollment/ingestion implemented (Rebuild Phase 5 Stage 2):** `modules/biometric_enrollment/` — a separate module from `modules/face_recognition/`, deliberately. It owns everything up to and including "a validated image is safely stored for a student"; it never detects, aligns, embeds, or matches a face, and adds no inference dependency (only Pillow, for decode/format/dimension validation). Two ORM tables (`BiometricEnrollment`, `BiometricSample`; migration `ca8e748dc8f2`, parent `e1208296dad5`) give clear separation between a student's enrollment *identity/lifecycle* and the individual stored *sample* files, each tracked through an explicit state machine (`pending` → `active` → `replacement_pending`/`deletion_pending` → `quarantined` → `deleted`) — see that module's `models.py` for the full rationale, and `docs/HANDOVER_PHASE_5_STAGE_2.md` for the design in detail. A `RecognitionProcessingState` column exists on every sample specifically so no Stage 2 code path could ever claim a sample is recognition-ready — Stage 3 is the first code to write anything other than `pending_processing` there (via `app/modules/face_recognition/processing_service.py`, which also added three nullable processing-bookkeeping columns to `biometric_samples` in the Stage 3 migration, without touching Stage 2's own migration file).
- Private storage (`modules/biometric_enrollment/storage.py`) is a filesystem abstraction with three zones under `BIOMETRIC_STORAGE_ROOT` — `staging/`, `active/`, `quarantine/` (plus `bulk_staging/` for whole-ZIP uploads) — addressed only by server-generated opaque keys; no client-supplied filename or path ever reaches a filesystem call. Promotion/quarantine are atomic same-filesystem renames (`os.replace`); every code path that pairs a database write with a filesystem rename documents and implements compensating cleanup for the case where the rename fails after the database write already committed (a SQL transaction cannot roll back a filesystem operation — see `docs/BIOMETRIC_DATA_POLICY.md`).
- Bulk enrollment accepts a ZIP archive with a root `manifest.csv` (`student_profile_id,filename` columns) and validates the entire archive — path traversal, absolute/drive/UNC paths, symlinks, encrypted/nested members, excessive count/size, suspicious compression ratios, and manifest consistency — before extracting a single byte (`modules/biometric_enrollment/zip_security.py`, never `ZipFile.extractall()`/`extract()`). The batch is atomic with respect to validation: any row failing pre-execution validation aborts the whole batch with zero writes.
- A narrowly-scoped, read-only reconciliation report (`modules/biometric_enrollment/reconciliation.py`) detects database/filesystem drift (an active-status row with no file, an orphaned file with no row, a sample stuck mid-transition) without ever repairing it automatically — consistent with this application having no background-worker architecture to run an automated repair job on.
- **No model weight of any kind (detector `.onnx` or embedder `.dat`) is downloaded, vendored, or committed anywhere in this repository or any ZIP built from it.** `Settings.FACE_DETECTOR_MODEL_PATH`/`FACE_EMBEDDER_MODEL_PATH` are deployer-supplied filesystem paths to files obtained independently, with optional SHA-256 integrity verification (`app/modules/face_recognition/model_artifacts.py`).

### Milestone 4 proposal and OTP boundaries

- Image attendance is proposal-first: one bounded upload may yield multiple
  face proposals inside a persisted non-biometric review envelope. No
  decision, including `FOUND`, writes attendance. Only the authorized
  teacher's explicit confirmation crosses into the existing
  `AttendanceService`; unmarked, missed, unknown, ambiguous, and duplicate
  faces remain non-writing. Uploaded classroom images and per-request
  embeddings stay in memory.
- `LOGIN_OTP_ENABLED=false` leaves the Phase 2 login contract unchanged. When
  enabled, credentials create a challenge containing only an HMAC-SHA256
  digest and lifecycle metadata. The existing access-token/refresh-session
  issuer is called only after the challenge is consumed successfully.
- OTP expiry, one-time use, attempts, resend replacement/cooldown, and endpoint
  limits are server-side. SMTP is environment configured; the explicit
  development-log adapter is rejected in production, and OTPs are never
  returned in API responses.

## 10. Frontend state & API flow

- Server state (anything from the API) lives in TanStack Query, not component state or Context — replaces the legacy pattern of manual `useState`/`useEffect` + direct axios calls with no caching, retry, or 401-handling (AUDIT §3.4).
- Auth state (current user, token) stays in a small React Context, but token storage strategy is revisited (legacy: `localStorage`, read independently from two places — `api.js` and `AuthContext.jsx` — AUDIT §3.4) in favor of a single source of truth, with httpOnly-cookie storage evaluated as an option during Phase 2.
- Every route the legacy app has gets rebuilt — including `/student/*`, which in the legacy app is wired to empty files and crashes at runtime (Critical C3). The rebuild's Student feature module is scoped explicitly in Phase 7 so this doesn't silently happen again.

## 11. Testing layers

- Backend: unit tests per module (`service`/`repository` logic), integration tests per API router, using a real (containerized) Postgres for integration tests rather than mocks where practical.
- Frontend: component tests (Vitest + RTL) per feature, Playwright e2e later for the critical paths (login → mark attendance → view report).
- This entire layer is new — the legacy app has the folder structure for it (`tests/unit/`, `tests/integration/`) but zero actual test code (AUDIT §2.12).

## 12. Deployment shape

- Root `docker-compose.yml` starts PostgreSQL 16, a one-shot Alembic migration
  gate, the non-root `backend_v2` runtime, and the non-root Nginx frontend.
- Only the frontend publishes a host port. It serves the SPA and proxies
  `/api/*` and `/health/*`; PostgreSQL and FastAPI remain private to Compose.
- PostgreSQL and private biometric storage use separate persistent named
  volumes. Source/release archives exclude biometric data and model weights.
- Environment config is centralized in Pydantic `Settings`. Production rejects
  placeholder/missing secrets, debug mode, wildcard/empty CORS or trusted-host
  lists, and insecure refresh cookies.
- GitHub Actions runs PostgreSQL migrations, the complete backend suite,
  production-source Ruff/mypy/compile checks, all frontend gates and dependency
  audits, Compose validation, and both production image builds.

## 13. Legacy → v2 migration strategy

See `docs/LEGACY_MIGRATION_MAP.md` for the full per-module breakdown. In summary:
- **Data:** a one-time export/transform/load from MongoDB collections into the new PostgreSQL schema, written as a real Alembic-adjacent script (not an ad hoc debug script) once Phase 1's schema is finalized. Legacy password hashes (Werkzeug scrypt) can be verified against the same algorithm during login without forcing a mass password reset, if desired — a decision to make explicitly at Phase 2, not assumed here.
- **Production retirement:** the Phase 9 Compose topology contains no Flask,
  MongoDB, or legacy CRA process. Historical source remains for traceability,
  but `backend_v2` + PostgreSQL + the Vite frontend are the only production
  application stack.
- **No functionality is silently dropped** — every legacy feature has an explicit Reuse/Refactor/Rewrite/Remove/Defer decision in the migration map, including the two features that turned out to be entirely unimplemented already (face recognition, student frontend) — those simply become greenfield work in Phases 5–7 rather than "migrations."

## 14. Phase 9 canonical and retirement boundary

- **`backend_v2/` is canonical.** It contains the complete FastAPI application:
  authentication/RBAC, academic management, attendance/audit, biometric
  enrollment and recognition attendance, and reports/exports.
- **PostgreSQL is the production source of truth.** No v2 process imports a
  Mongo client or performs a dual write.
- **`frontend/` is canonical.** It is the strict TypeScript/Vite application for
  all three roles and the only frontend built into the production image.
- **Legacy source is retained, not deployed.** `backend/` and historical legacy
  files remain available for audit/migration reference, but no Dockerfile,
  Compose service, Nginx route, startup command, or CI application job executes
  them.
- **Historical data conversion remains deployment-specific.** A school moving
  real legacy MongoDB records must run a separately reviewed export/transform/
  validate/import procedure. The release never connects both databases or
  silently imports production data.
