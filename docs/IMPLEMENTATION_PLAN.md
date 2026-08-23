# ShikshaSathi v2 — Phased Implementation Plan

Grounded in `docs/AUDIT.md` and `docs/LEGACY_MIGRATION_MAP.md`. Each phase lists Goal, Scope, Deliverables, Dependencies, Acceptance criteria, Verification commands, and explicit out-of-scope work.

---

## Phase 0: Audit, cleanup, architecture, migration plan
**Status: this phase, completed this session — see `docs/PROGRESS.md`.**
- **Goal:** a verified, repository-grounded foundation to rebuild from.
- **Scope:** audit, safe cleanup, `.env.example`, migration map, architecture, ADRs, this plan, progress tracking, handover.
- **Deliverables:** `docs/AUDIT.md`, `docs/LEGACY_MIGRATION_MAP.md`, `docs/ARCHITECTURE.md`, `docs/adr/0001-0005`, `docs/IMPLEMENTATION_PLAN.md` (this file), `docs/PROGRESS.md`, `docs/HANDOVER_PHASE_0.md`, `backend/.env.example`, updated `.gitignore`.
- **Dependencies:** none.
- **Acceptance criteria:** all documents above exist and are grounded in actual repository inspection (not templated guesses); no source code behavior changed; no commit created.
- **Verification commands:** `git status --short`; manual review of each doc against `docs/AUDIT.md`'s evidence.
- **Out of scope:** any FastAPI/PostgreSQL/TypeScript code, any git commit, any deletion of files with uncertain purpose (`backend/debug_db.py`, `backend/fix_db.py` — kept and documented, not deleted).

---

## Phase 1: Backend foundation and PostgreSQL setup
**Status: this phase, completed this session — implemented under `backend_v2/` per the coexistence strategy in `docs/ARCHITECTURE.md` §14. See `docs/PROGRESS.md` and `docs/HANDOVER_PHASE_1.md`.** The scope, deliverables, and acceptance criteria below were followed as originally planned in Phase 0 — no decision in this phase changed, so no new ADR was required (see `docs/HANDOVER_PHASE_0.md`'s guidance to document any changed decision in a new ADR before changing it). One addition beyond the original text below: `docker compose up` could not be executed in the Phase 1 implementation environment (no Docker, no network egress) — see `docs/PROGRESS.md` for exactly what was and wasn't verifiable, and for the honest accounting of which acceptance criteria are code-complete versus runtime-verified.
- **Goal:** a running FastAPI skeleton against a real Postgres database, with no business features yet.
- **Scope:** `pyproject.toml`, FastAPI app skeleton, `core/config.py` (Pydantic Settings — closes AUDIT §1.8/§2.3's scattered-`os.getenv` finding), SQLAlchemy 2 engine/session setup, Alembic initialized with an initial schema migration, `docker-compose.yml` (Postgres + backend), structured logging (`core/logging.py`, closes AUDIT §2.7).
- **Deliverables:** running `docker compose up` bringing up backend + Postgres; `/health` that actually checks DB connectivity (closes AUDIT §2.2's shallow-health-check finding); Alembic `upgrade head` works from empty.
- **Dependencies:** Phase 0 complete.
- **Acceptance criteria:** `GET /health` returns healthy only when Postgres is actually reachable; app fails to start (not silently degrades) if required config is missing — directly closes the "silent `_db = None`" pattern (AUDIT §2.2) and the JWT-secret-fallback pattern (AUDIT §2.3/C2), since config loading is centralized and validated at startup.
- **Verification commands:** `docker compose up`, `curl localhost:8000/health`, `alembic upgrade head`, `alembic downgrade base && alembic upgrade head` (round-trip check).
- **Out of scope:** authentication, any domain model beyond what Alembic needs to prove the pipeline works, any frontend work.

---

## Phase 2: Authentication, refresh-token security, RBAC, ownership checks
- **Goal:** close Critical findings C2 and C4.
- **Scope:** login endpoint, password hashing (carry forward Werkzeug/scrypt approach or equivalent — AUDIT §2.3 positive finding), access + refresh tokens, role-check dependency, **object-level ownership-check dependency** (the direct fix for C4 — teacher↔classroom assignment verified before any attendance read/write), rate limiting on `/auth/login` (closes H1), consolidation of what used to be two overlapping decorators (`requires_roles`/`token_required`, AUDIT §2.4) into one dependency-injection-based approach.
- **Deliverables:** working login/refresh/logout; every teacher-scoped route protected by both role AND ownership checks; login rate-limited.
- **Dependencies:** Phase 1.
- **Acceptance criteria:** a test user with role `teacher` cannot read or write attendance for a classroom they are not assigned to (this is the concrete regression test for C4); `/auth/login` returns 429 after N rapid failed attempts; app refuses to start with no `JWT_SECRET`/equivalent set (no fallback default, closes C2).
- **Verification commands:** integration tests exercising both the "allowed" and "forbidden" ownership paths; a scripted rapid-login-attempt test against the rate limiter.
- **Out of scope:** the frontend auth UI beyond what's needed to exercise these endpoints in tests; face recognition; academic domain CRUD beyond the minimum needed to test ownership (e.g. one classroom, one teacher assignment).

---

## Phase 3: Academic domain models and management APIs
- **Goal:** classrooms, subjects, teachers, students, timetable, announcements as real relational data with full CRUD.
- **Scope:** SQLAlchemy models + Alembic migrations for the full academic domain; FastAPI routers per module (`docs/ARCHITECTURE.md` §2); CSV/Excel import with validation and row limits (closes AUDIT §2.10's unguarded `pd.read_excel` finding); timetable/announcement logic ported from the legacy `models/timetable.py`/`models/announcement.py` (the actually-used implementations, not the dead `services/*_service.py` files — AUDIT, Legacy Migration Map).
- **Deliverables:** full admin CRUD for students/teachers/classrooms/subjects; timetable and announcements working end-to-end; bulk import with per-row error reporting.
- **Dependencies:** Phase 2 (all these routes are role/ownership protected).
- **Acceptance criteria:** a malformed bulk-import file produces a clear per-row error list instead of an unhandled 500 (regression test for AUDIT §2.10); every write endpoint validates through a Pydantic model.
- **Verification commands:** `pytest backend/app/tests -k academics`; a scripted malformed-Excel-upload test.
- **Out of scope:** attendance itself (Phase 4), face recognition (Phase 5), any frontend work beyond what's needed for API contract testing.

---

## Phase 4: Attendance core and audit trail
- **Status (2026-08-01): COMPLETE.** Stages 1-4 are implemented and authoritatively verified against PostgreSQL: 98 targeted Phase 4 tests passed; the complete backend suite passed with 311 tests; Ruff format, Ruff lint, and mypy passed; Alembic head/current are `e1208296dad5`.
- **Goal:** attendance marking/query/export, fully authorized and audited.
- **Scope:** attendance schema + transactional bulk-save (closes AUDIT §6's transaction-handling gap — a partial batch failure can no longer leave inconsistent rows); stats/detail/export endpoints, all behind the Phase 2 ownership-check dependency; audit-log coverage extended to include blocked/forbidden attempts, not just successful admin actions (extends the legacy audit-log feature, AUDIT §2.4/Legacy Migration Map "Audit logs" row).
- **Deliverables:** attendance marking, per-student/per-classroom stats, CSV export, audit trail of who marked/changed what.
- **Dependencies:** Phase 3 (needs classrooms/subjects/students to exist).
- **Acceptance criteria:** a bulk-attendance-save that fails partway through rolls back entirely (no partial writes); every attendance write is attributable to a user in the audit log; a blocked ownership-check attempt is itself logged.
- **Verification commands:** `pytest backend/app/tests -k attendance`; a scripted "kill the process mid-batch" or forced-exception test against the transactional save.
- **Out of scope:** face-recognition-based auto-marking (Phase 5); reports/analytics beyond raw stats (Phase 8).

---

## Phase 5: Face enrollment and recognition workflow
- **Status (2026-08-16): COMPLETE.** Stages 1-4 remain as delivered in their
  authoritative handovers. Stage 5 completed the real Docker/PostgreSQL runtime,
  failure-path, concurrency, migration, full-suite, and release gates. See the
  consolidated `docs/HANDOVER_PHASE_5.md`.
- **Goal:** an actual, working face-recognition pipeline — the legacy app never had one (AUDIT §2.13/H3).
- **Dependencies:** Phase 3 (student records must exist to enroll faces against); ADR 0005 resolved (**done, this session** — Accepted, see `docs/adr/0005-face-recognition-provider-pending.md`).
- **Out of scope for the phase as a whole:** any frontend camera-capture UI polish beyond making enrollment/matching functionally testable (deeper UX belongs to Milestone 2).

Phase 5 is executed in five stages, each its own checkpoint with its own handover document, exactly as Phases 3 and 4 were:

### Stage 1: Provider decision and biometric foundation
- **Scope:** resolve `docs/adr/0005-face-recognition-provider-pending.md` to `Accepted` with a concrete, sourced comparison (not a vague "best accuracy" claim); create the provider-neutral `detect`/`embed`/`match` contracts and `Protocol` interfaces (`app/modules/face_recognition/domain.py`, `protocols.py`); stable domain errors (`errors.py`); fail-fast configuration (`app/core/config.py`); `docs/BIOMETRIC_DATA_POLICY.md`.
- **Deliverables:** Accepted ADR 0005; `app/modules/face_recognition/` package (contracts/protocols/errors only — no inference, no router); Stage 1 config surface; biometric data policy; focused contract/config tests.
- **Explicitly out of scope:** any real detection/embedding/matching code, any enrollment endpoint, any ORM table/migration, any new inference dependency (`opencv-python-headless` is deferred to Stage 3; `onnxruntime` is further deferred still, only if a selected embedding-model adapter needs it — the YuNet detector itself does not), any model file download.
- **Acceptance criteria:** ADR 0005 is `Accepted`; invalid contract inputs (bad dimensions/bounding boxes/embeddings/confidence values) are rejected with tests proving it; invalid configuration (provider/device/threshold/margin/storage-root) is rejected with tests proving it; a deterministic test double satisfies each Protocol.
- **Verification commands:** `pytest backend_v2/app/tests -k face_recognition`; `pytest backend_v2/app/tests/test_config.py -k face`.

### Stage 2: Face enrollment and secure photo ingestion
- **Status: COMPLETE this session — see `docs/HANDOVER_PHASE_5_STAGE_2.md`.**
- **Scope:** admin-only enrollment endpoint(s); validated single-photo and bulk-photo (ZIP) ingestion with per-entry path validation before extraction, replacing the legacy zip-slip-vulnerable pattern (AUDIT §2.11/H4) from the start rather than porting it; storage under `Settings.BIOMETRIC_STORAGE_ROOT`, never web-root-derived from an uploaded filename.
- **Deliverables:** enrollment create/replace/delete; secure bulk photo import; audit-logged enrollment events (reusing the Phase 4 `AuditLog` pattern). Delivered as `app/modules/biometric_enrollment/` (models, storage, image validation, ZIP security, service, bulk service, router, reconciliation), migration `ca8e748dc8f2` (parent `e1208296dad5`), and the tests/docs listed in `docs/HANDOVER_PHASE_5_STAGE_2.md`.
- **Dependencies:** Stage 1 (contracts, policy, config) and Phase 3 (student records to enroll against).
- **Acceptance criteria:** a bulk photo-zip upload containing a path-traversal entry (e.g. `../../evil.jpg`) is rejected before extraction, with a test proving it (direct regression test for H4, `test_phase5_stage2_zip_security.py::test_path_traversal_dotdot_is_rejected_before_extraction` and the HTTP-level equivalent in `test_phase5_stage2_bulk_zip_http.py`) — **met**; a non-admin cannot enroll — **met** (role-gated at the router; see the biometric data policy's admin-only decision); every enrollment/replacement/deletion is audited — **met**.
- **Explicitly out of scope:** detection/embedding/matching itself (Stage 3); any recognition-triggered attendance write (Stage 4). Confirmed not started — see `docs/HANDOVER_PHASE_5_STAGE_2.md`'s "Stage 3 starting point".

### Stage 3: Detection, embedding, and matching pipeline
- **Status: COMPLETE this session — see `docs/HANDOVER_PHASE_5_STAGE_3.md` and `docs/adr/0011-phase5-stage3-embedding-model-and-matching.md`.**
- **Scope:** the first real implementations of `FaceDetector`/`FaceEmbedder`/`FaceMatcher` (per ADR 0005: YuNet loaded through OpenCV's DNN/`FaceDetectorYN` API as detector; embedding model per ADR 0005's deferred licensing resolution), wired to Stage 2's stored enrollment data. `opencv-python-headless` and `dlib` added here; `onnxruntime` deliberately not added (neither the YuNet detector nor the selected dlib embedder needs it).
- **Deliverables (delivered):** a standalone alignment/normalization stage (`app/modules/face_recognition/alignment.py`) between detection and embedding; working detect→align→embed→match against enrolled students, candidate-scoped (never institution-wide); a new `biometric_embeddings` table and migration `d22bce264ecd` (parent `ca8e748dc8f2`); `ProviderHealth` reporting (`app/modules/face_recognition/health.py`); a FAR/FRR/threshold-sweep evaluation harness (`app/modules/face_recognition/evaluation.py`, synthetic data only); admin-only APIs for sample processing/retry/status/health/match-probe validation (`app/modules/face_recognition/router.py`).
- **`FACE_MATCH_THRESHOLD`/`FACE_MATCH_AMBIGUOUS_MARGIN`:** resolved to `0.82`/`0.05` — but recorded honestly, per the acceptance criterion below, as a **provisional structural default** (mathematically derived from dlib's own published Euclidean-distance guidance via the L2-normalized cosine/distance identity), **not** a value calibrated against this project's own classroom data. Real calibration remains explicitly pending — see the Stage 3 handover's "Calibration status."
- **Dependencies:** Stage 2 (enrolled biometric data to match against) — **met**.
- **Acceptance criteria:** an end-to-end detect→align→embed→match pipeline exists and is exercised by DB-backed tests using deterministic fake providers (real model files are not available in the sandbox this session was executed in — see the Stage 3 handover's "Unavailable checks"; the equivalent test against real vendored model files, and any measured accuracy, is Stage 5 territory, consistent with this plan's own "Docker/PostgreSQL/full runtime verification" split); **no accuracy claim is made anywhere in this codebase without saying explicitly that it is an uncalibrated, provisional structural default** — met, see the Stage 3 handover and ADR 0011.
- **Explicitly out of scope, and confirmed not started:** any HTTP-facing recognition-*attendance* endpoint, any `AttendanceService` call, any `AttendanceRecord` write (Stage 4) — see the Stage 3 handover's "Exact Stage 4 starting point" for the explicit, verified confirmation.

### Stage 4: Recognition attendance workflow and APIs
- **Status: COMPLETE.** Delivered in `docs/HANDOVER_PHASE_5_STAGE_4.md`; Stage 3's provider pipeline and Phase 4's attendance core remain the reused boundaries.
- **Scope:** a router in `app/modules/face_recognition/` that accepts a classroom-scoped recognition image, runs detect→embed→match for all bounded faces, and returns proposals. Every result—including `FOUND`—requires explicit teacher review and confirmation before selected records are written through the existing Phase 4 `AttendanceService`, per `docs/BIOMETRIC_DATA_POLICY.md`.
- **Deliverables:** teacher-facing recognition-attempt endpoint(s), still behind the Phase 2 ownership-check dependency (a teacher may only trigger recognition for their own assigned classroom); every recognition decision audited.
- **Dependencies:** Stage 3 (a working pipeline — **met**, this session) and Phase 4 (`AttendanceService`, reused unmodified).
- **Acceptance criteria:** no recognition result writes attendance before explicit confirmation; multi-face, unknown, ambiguous, duplicate, and no-face results remain safe proposals; confirmed selected records use `AttendanceService`; the recognition/provider layer never calls attendance-writing code directly (a structural/import-boundary check, not just a code-review note).
- **Explicitly out of scope:** the final Docker/pytest/Ruff/mypy authoritative gate and Phase 5 closure sign-off (Stage 5).

### Stage 5: Runtime verification, hardening, and Phase 5 closure
- **Status (2026-08-16): COMPLETE.** Fresh PostgreSQL migrations reached
  `4f8c1a6e92b7 (head)` and all six migration tests executed; 217 combined
  Phase 5 plus Phase 4 `AttendanceService` tests passed; the complete backend
  suite passed **675/675** with no skips. The Stage 2 response-serialization
  `MissingGreenlet` defect and stale closure tests were corrected, retry and
  concurrent-confirmation invariants were proven against PostgreSQL, the
  production runtime image built, and both live/ready health probes passed.
  Changed application services pass strict mypy and scoped Ruff checks. Global
  Ruff/mypy findings are recorded historical debt rather than closure defects;
  no broad cleanup was performed. Phase 6 remains not started.
- **Scope:** the same authoritative-verification pattern Phase 4 closed with (`docs/HANDOVER_PHASE_4.md`) — run the full Docker/PostgreSQL/pytest/Ruff/mypy gate against Stages 1–4's combined work, fix any genuine finding, re-verify AUDIT §2.11/H4 and §2.13/H3 are closed with passing (not just written) tests, and write the consolidated `docs/HANDOVER_PHASE_5.md`.
- **Deliverables:** authoritative test/lint/type-check results; consolidated Phase 5 handover; confirmation that no accuracy claim in any prior stage's docs was left unverified.
- **Dependencies:** Stages 1–4 complete.
- **Acceptance criteria:** matches Phase 4's closure bar — every acceptance criterion from Stages 1–4 has a corresponding closed/verified item, not just an implemented one.
- **Out of scope:** anything not already scoped in Stages 1–4 (no new feature is introduced at closure time).

---

## Phase 6: React TypeScript frontend foundation
**Status (2026-08-16): COMPLETE.** The legacy CRA shell was replaced by the
strict TypeScript/Vite application documented in `docs/HANDOVER_PHASE_6.md`.
All three role shells render, centralized cookie-backed refresh handling is
covered, and the required typecheck/build/test/lint gates pass. Phase 7 was not
started.
- **Goal:** a working Vite + TypeScript app shell with routing and API integration, replacing CRA.
- **Scope:** project scaffold (`docs/ARCHITECTURE.md` §2), typed API client + TanStack Query setup, auth context/token-storage decision made and implemented (closes AUDIT §3.4's two-places-touch-localStorage finding and adds a 401-response interceptor, which the legacy app has none of), routing for **all three roles including Student** (direct fix for Critical C3 — the legacy app's `StudentRoutes.jsx`/`StudentLayout.jsx` were empty and crashed at runtime).
- **Deliverables:** app shell that builds and type-checks with zero `any`-typed route imports; login flow; role-based route guards for admin/teacher/student, all three actually implemented.
- **Dependencies:** Phase 2 (needs a real login endpoint to integrate against).
- **Acceptance criteria:** `tsc --noEmit` passes with no errors; a test asserting `/student/*` renders without throwing (the direct regression test for C3, which had zero such coverage in the legacy app).
- **Verification commands:** `npm run build`, `npm run typecheck`, `vitest run`.
- **Out of scope:** full feature pages for each role (Phase 7); reports/analytics UI (Phase 8).

---

## Phase 7: Admin, Teacher, and Student workflows
- **Status (2026-08-16): COMPLETE.** Full details and exact verification
  evidence are in `docs/HANDOVER_PHASE_7.md`. Phase 8 has not started.
- **Goal:** full feature parity with the legacy Admin/Teacher UI, plus an actually-functioning Student portal for the first time.
- **Scope delivered:** admin CRUD for classrooms, subjects, profiles,
  membership, assignments, timetable, announcements, and imports; teacher
  profile/class/subject/timetable views plus manual and recognition attendance;
  student self profile, attendance summary/detail/filtering, and announcements.
- **Integration correction:** after a proven blocker and explicit approval,
  added `GET /attendance/roster` using the existing exact-scope attendance
  authorization. This was a Phase 7 unblocker, not historical Phase 5 work.
- **Deliverables:** feature-complete UI for all three roles, typed Phase 7 API
  modules/DTOs, reusable admin CRUD state, responsive workflow styles, and
  focused API/component tests.
- **Dependencies:** Phase 6; Phase 3/4 backend endpoints.
- **Acceptance criteria:** student routes use only `/student-profiles/me` and
  `/attendance/me/*`; component/API tests prove their wiring without accepting
  arbitrary student IDs. A live three-role browser-to-backend smoke test was
  not available and is explicitly deferred rather than claimed.
- **Verification:** typecheck, build, lint, and npm audit passed; 6 frontend
  test files / 28 tests passed. Focused roster tests passed 5 and the broader
  attendance regression set passed 52.
- **Out of scope:** advanced analytics/leaderboards (Phase 8); accessibility/responsiveness polish beyond a working baseline (flagged in AUDIT §3.7 as unassessed in the legacy app — full pass is Milestone 2 territory unless a blocking issue surfaces earlier).

---

## Phase 8: Reports, exports, and analytics
- **Status (2026-08-17): COMPLETE.** The authoritative implementation and
  verification record is `docs/HANDOVER_PHASE_8.md`. Phase 9 has not started.
- **Goal:** the reporting/analytics surface (`api/v1/reports.py`, defaulters list, classroom leaderboard) rebuilt and verified — this was only spot-checked, not deeply audited, in Phase 0 (`docs/LEGACY_MIGRATION_MAP.md`, Reports row).
- **Scope:** report endpoints + UI and CSV/PDF export (legacy frontend had
  `jspdf`/`html2pdf.js` dependencies for this). The announcement feed moved to
  and was completed in Phase 7.
- **Deliverables delivered:** exact-scope Admin/Teacher attendance report,
  active-roster defaulters, deterministic classroom leaderboard, formula-safe
  CSV, bounded in-memory multi-page PDF, typed Admin/Teacher Reports UI, and
  focused backend/frontend verification. Student arbitrary-report access is
  deliberately absent.
- **Dependencies:** Phase 4 (attendance data), Phase 7 (UI shell).
- **Acceptance criteria:** met. Exported report counts were spot-checked against
  a direct PostgreSQL query; report/export tests, full regressions, static
  checks, Docker build, frontend build/tests/lint, and dependency audit passed.
- **Verification:** see `docs/HANDOVER_PHASE_8.md` for exact commands, counts,
  security/privacy gates, and the recorded historical global Ruff/mypy debt.
- **Out of scope:** anything not already present in the legacy app's reports scope — no new analytics invented here beyond parity plus the fixes already implied by earlier phases.

---

## Phase 9: Tests, Docker, CI, deployment, security hardening
- **Status (2026-08-17): COMPLETE.** The authoritative implementation,
  verification, deployment, security-closure, and release record is
  `docs/HANDOVER_PHASE_9.md`. The Deployable MVP is complete; Milestone 2 has
  not started.
- **Goal:** production readiness — met.
- **Scope delivered:** complete backend/frontend suites, production backend
  and frontend images, a PostgreSQL/FastAPI/nginx Compose stack with a
  deterministic Alembic gate, GitHub Actions CI, final C1–C4/H1–H5 closure,
  secrets/privacy/dependency scans, current README/API documentation, and a
  release-filtered clean-source reproduction.
- **Deliverables:** delivered. CI definition, production-shaped images and
  Compose, accurate root/backend/frontend/API documentation, final handover,
  and the cumulative Phase 9 artifact are present.
- **Dependencies:** all prior phases.
- **Acceptance criteria:** met for the rebuilt v2 runtime. Every original
  Critical/High finding has a closure/evidence record; CI is configured for
  pull requests and `main`; clean-source installs/builds, fresh migrations,
  production Compose, health, and frontend/API routing passed. Hosted CI and
  a literal independent fresh clone remain post-publication human validation
  because Phase 9 explicitly prohibited Git operations.
- **Verification:** 718 backend tests passed against PostgreSQL; Ruff, mypy,
  compileall, frontend typecheck/lint/40 tests/build, npm audit, pip-audit,
  clean-source production images, migration to `4f8c1a6e92b7`, and runtime
  smoke all passed. See `docs/HANDOVER_PHASE_9.md` for exact results.
- **Out of scope:** anything explicitly deferred to Milestone 2 below.

---

## Milestone 1: Deployable MVP
**Status (2026-08-17): COMPLETE.**

Core auth (Phase 2), roles, academic management (Phase 3), attendance (Phase 4), basic face recognition (Phase 5), dashboards for all three roles (Phase 6–7), reports (Phase 8), Docker + deployment (Phase 9). This is the point at which the legacy Flask/CRA app can actually be retired.

## Milestone 2: Portfolio Edition
**Status: NOT STARTED.**

Advanced UX polish, accessibility pass (unassessed in the legacy app per AUDIT §3.7 — first real pass here), deeper analytics, monitoring/observability, stronger test coverage (property-based/fuzz tests for the areas that had real bugs — zip-slip §2.11, ownership §2.4), performance work, and biometric lifecycle polish (consent flows, retention automation) beyond the baseline policy established in Phase 5.
