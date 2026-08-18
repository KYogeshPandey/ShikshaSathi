# Phase 5 final handover

## Closure status

**Phase 5 is complete as of 2026-08-16.** This is the consolidated,
authoritative handover for Stages 1-5. Phase 6 was not started. No frontend or
new feature work was performed, no model artifact was downloaded, and no Git
operation was performed.

The locked Stage 4 input artifact was verified before closure. Its SHA-256 was
`5ec3b280892ad3da5330f39e6142ab359eb9ce121f592ab7dffd57424e49fcea`,
matching the recorded value.

## What Phase 5 delivers

1. **Stage 1 — provider-neutral foundation.** Accepted ADR 0005, typed
   detection/embedding/matching contracts, provider protocols, stable domain
   errors, fail-fast settings, and the biometric data policy.
2. **Stage 2 — private enrollment ingestion.** Admin-authorized single and
   bulk-ZIP enrollment, validation before extraction, private staged storage,
   lifecycle/audit handling, deletion, and reconciliation. Neither raw images
   nor storage paths are returned by the API or stored in audit metadata.
3. **Stage 3 — recognition pipeline.** YuNet/OpenCV detection, landmark
   alignment, dlib 128-dimensional L2-normalized embeddings, candidate-scoped
   cosine matching, provider health, processing/retry, and a synthetic
   FAR/FRR/threshold-sweep harness.
4. **Stage 4 — recognition attendance.** Server-derived active classroom
   roster, teacher ownership enforcement before image inference, persisted
   recognition attempts, `FOUND` attendance through the existing Phase 4
   `AttendanceService`, and explicit confirmation for `UNKNOWN`/`AMBIGUOUS`.
5. **Stage 5 — runtime closure.** Fresh PostgreSQL migration execution,
   failure-path and concurrency hardening, Docker production/test builds,
   health probes, complete backend pytest execution, quality/security checks,
   documentation, and release packaging.

This closes the original audit's H3 finding: the backend now has an exercised
detect → align → embed → candidate-scoped match pipeline and a separately
authorized attendance workflow. It also closes H4: archive entries are
validated before use and traversal/absolute/drive/UNC/symlink/encryption/
nesting/compression-limit cases have passing regression coverage; production
code never calls `ZipFile.extract()` or `extractall()`.

## Provider, licensing, and calibration status

Inference remains local, server-side Python behind provider protocols. YuNet
is loaded through OpenCV's `FaceDetectorYN`; dlib supplies the 128-D embedding
model adapter. The dlib *library* is Boost Software License 1.0, while the
selected model weight is separately described by its author as public domain.
Those are distinct licensing facts. The training-data provenance caveat in ADR
0011 remains disclosed.

No model weights are committed or packaged. The face-match threshold `0.82`
and ambiguity margin `0.05` remain provisional structural defaults, not
project-data calibration and not an accuracy claim. The synthetic evaluation
harness tests its own math but does not establish real-world performance.

**REAL MODEL SMOKE TEST: NOT RUN.** Vetted detector and embedder model
artifacts were unavailable. Stage 5 did not download models and did not use
images of real people.

## Security and attendance invariants

- Biometric images stay under the configured private storage root. API and
  audit response shapes exclude image bytes, filesystem paths, embeddings, and
  raw infrastructure exceptions.
- Enrollment is admin-authorized. Recognition attendance is teacher-scoped
  through the existing classroom ownership dependency.
- Active student candidates are derived from the classroom roster on the
  server. There is no institution-wide recognition fallback.
- Provider work is reached only after authorization and roster derivation.
- The provider/matcher layer does not construct attendance records or import
  an attendance repository. Attendance writes go through `AttendanceService`.
- `FOUND` creates one idempotent PRESENT state. `UNKNOWN` and `AMBIGUOUS`
  create no automatic attendance. Explicit confirmation rechecks ownership and
  active membership, row-locks the attempt, rejects cross-classroom/student
  conflicts, and is idempotent under repeated and concurrent requests.
- Attempts and decisions are auditable. Persisted audit metadata is bounded and
  contains identifiers/outcomes only, not biometric material.
- Image decoding keeps Pillow's process-global pixel guard unchanged. Blocking
  provider calls are offloaded, and provider instances use their own locks.

## Stage 5 defects and corrections

### Stage 2 `MissingGreenlet`

The failure was reproduced against real PostgreSQL before the correction. An
SQLAlchemy column using `onupdate=func.now()` left `updated_at` expired after
the activation flush. Pydantic response validation after commit then tried an
implicit async ORM load outside the greenlet context.

The smallest service-boundary fix explicitly refreshes the affected ORM row
and constructs the safe Pydantic response while the async transaction/session
is active. The same boundary was hardened for replacement and deletion.
Primitive UUIDs are captured before operations that can roll back so
compensation and logging never dereference rollback-expired ORM objects. A
dedicated PostgreSQL regression asserts a successful response with a
timezone-aware `updated_at`.

### Category-C closure failures

The two originally reported unrelated failures were investigated rather than
masked:

- The Phase 4 migration regression assumed its historical revision was the
  repository head. It now moves explicitly through Phase 4 and restores the
  real Phase 5 head; migration source was not rewritten.
- Replacing an enrollment with no active sample returned a generic 404 even
  though the route/service contract defines the stable
  `ENROLLMENT_NO_ACTIVE_SAMPLE` 409. The service now raises that precise
  conflict and the HTTP test asserts it.

Closure also exposed stale test expectations for ASGITransport exception
propagation, the bulk result field name, and a Stage 3 replacement terminal
state. Those tests were aligned to the already-defined production contracts.
A Stage 4 test stopped retaining an expirable actor ORM object across an
independent commit. None of these changes redesigned a stage or changed a
migration.

### Failure and concurrency hardening

- A `FOUND` attempt is committed independently from attendance mutation. An
  injected `AttendanceService` failure therefore leaves an auditable unlinked
  attempt and no partial attendance; retry converges to exactly one attendance
  row and one linked attempt.
- Two independent PostgreSQL sessions confirming the same pending attempt are
  serialized by `FOR UPDATE`. Both callers receive the same outcome, with one
  attendance state and one successful confirmation audit.
- A second confirmation naming a different student is rejected with the
  stable conflict response and creates no second attendance row.
- Enrollment storage promotion/quarantine failures preserve recoverable state
  and are covered by failure-injection tests.

## Migration result

An empty, isolated Compose `postgres_test` database (PostgreSQL 16, tmpfs) was
created; no development or production database was used. The full chain ran:

`base → 98161483914f → 6eeb9420bf8b → 32819e0a6027 → e1208296dad5 → ca8e748dc8f2 → d22bce264ecd → 4f8c1a6e92b7`

`alembic current` before and after the migration test gate was
`4f8c1a6e92b7 (head)`. All six migration tests passed with zero skips. The
Stage 4 round trip executed:

`d22bce264ecd → 4f8c1a6e92b7 → d22bce264ecd → 4f8c1a6e92b7`

## Exact runtime and test results

- Docker daemon: reachable; Docker Engine 29.6.2 and Compose 5.3.1.
- Fresh repository test image: built successfully, including native dlib
  compilation after adding CMake/build tools to the build/test stages.
- Production runtime target: built successfully; build tools remain outside
  the final runtime stage.
- Runtime probes against PostgreSQL:
  - `/health/live`: `200 {"status":"alive"}`
  - `/health/ready`: `200 {"status":"ready","checks":{"database":"ready"}}`
- Enrollment/failure-injection/Phase 4 migration correction gate:
  **33 passed**.
- Former Stage 2 fallout plus Stage 3/4 hardening gate: **36 passed**.
- All migration tests: **6 passed, 0 skipped**.
- Complete Phase 5 plus Phase 4 `AttendanceService` gate: **217 passed**.
- Final affected-files gate from the freshly rebuilt test image: **62 passed,
  0 skipped**.
- Complete backend pytest suite, run once: **675 passed, 0 failed, 0 skipped,
  13 warnings** in 189.61 seconds.

The once-run complete suite therefore classified test failures as:

- **A — introduced by Stage 5/Phase 5: 0**
- **B — Stage 2 `MissingGreenlet`: 0**
- **C — unrelated historical failure: 0**
- **D — environment/infrastructure failure: 0**

The 13 warnings are non-failing deprecations from Starlette/httpx, HTTP status
constants, and per-request cookies, plus the deliberate duplicate-ZIP fixture
warning.

## Quality gates

- `python -m compileall -q app alembic scripts`: passed.
- Ruff format check on all seven Stage 5-modified Python files: passed
  (**7 already formatted**).
- Scoped Ruff lint on Stage 5 work: passed. One unchanged SIM117 in the older
  Stage 3 processing test remains outside the line changed by Stage 5.
- Strict mypy on the two changed application services: passed with no issues.
- Repository-wide `ruff format --check .`: historical baseline remains; 14
  older files would be reformatted.
- Repository-wide `ruff check .`: 23 historical findings remain, principally
  in Stage 3 providers/helpers/tests. None is a Stage 5 application defect.
- Repository-wide `mypy app` under mypy 1.20.2: 206 historical typing errors
  in 20 files (194 files checked). The two modified application services are
  clean. No broad formatting, lint, typing, dependency, or migration cleanup
  was performed.

## Security and release scans

- No secret/private-key token patterns or credential assignments were found.
- The only `.env` used was a temporary local file containing fake Compose test
  values; it was removed before packaging and is not in the release.
- No model-weight files, exported embedding artifacts, or biometric image
  artifacts were found or packaged.
- No current machine-specific absolute path was introduced. An older Stage 3
  handover retains a historical build-environment path observation and was
  intentionally not rewritten.
- Source-boundary scans confirmed candidate-scoped matching and
  `AttendanceService`-only attendance mutation.

## Exact files changed in Stage 5

1. `backend_v2/Dockerfile`
2. `backend_v2/app/modules/biometric_enrollment/service.py`
3. `backend_v2/app/modules/biometric_enrollment/bulk_service.py`
4. `backend_v2/app/tests/test_phase5_stage2_enrollment_http.py`
5. `backend_v2/app/tests/test_phase5_stage2_failure_injection.py`
6. `backend_v2/app/tests/test_migrations_phase4.py`
7. `backend_v2/app/tests/test_phase5_stage3_processing_service.py`
8. `backend_v2/app/tests/test_phase5_stage4_recognition_attendance.py`
9. `backend_v2/README.md`
10. `docs/HANDOVER_PHASE_5.md`
11. `docs/IMPLEMENTATION_PLAN.md`
12. `docs/PROGRESS.md`

No migration file, prior stage handover, legacy backend/frontend file, model
artifact, real `.env`, or Git state was changed.

## Remaining risks and deliberately deferred work

- Real detector/embedder model smoke testing is pending until vetted artifacts
  are supplied through deployment configuration.
- Classroom-domain calibration and fairness/accuracy evaluation are pending;
  the current threshold is explicitly provisional.
- Repository-wide historical Ruff and mypy debt remains as quantified above.
- Native dlib compilation makes a cold Docker test build slow, although the
  corrected targets build successfully.
- Operational monitoring, CI/deployment automation, production load testing,
  retention execution, and user-facing biometric consent/UX remain later-phase
  concerns.

These are disclosed risks, not hidden closure claims. They do not change the
verified Phase 5 API, persistence, authorization, and transaction invariants.

## Exact Phase 6 starting point

Phase 6 remains **NOT STARTED**. Its first authorized work is the Vite + React
TypeScript application shell defined in `docs/IMPLEMENTATION_PLAN.md`: typed API
client, one token-storage/auth-context decision, 401 handling, and working
admin/teacher/student route guards. No Phase 6 scaffold or frontend source was
created during this closure.
