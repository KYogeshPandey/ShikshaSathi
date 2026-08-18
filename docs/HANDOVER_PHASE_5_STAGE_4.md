# Phase 5 Stage 4 handover — recognition attendance workflow and APIs

**Status: Stage 4 implementation complete. Stage 5 and Phase 6 were not started.**

## Architecture delivered

Stage 4 adds one orchestration service,
`app.modules.face_recognition.recognition_attendance_service.RecognitionAttendanceService`,
and two teacher/admin routes under the existing face-recognition router:

- `POST /api/v1/face-recognition/attendance/attempts`
- `POST /api/v1/face-recognition/attendance/attempts/{attempt_id}/confirm`

The attempt route accepts `classroom_id`, `subject_id`, `attendance_date`, and
one still image. It never accepts candidate IDs, an embedding, or a matcher
result from the client.

## Authorization and candidate roster

Before the upload is read, decoded, validated, or sent to inference, the
orchestrator calls the existing Phase 4
`AttendanceReadService.authorize_scope`. This preserves admin/teacher role
semantics, exact active teacher assignment checks, concealed teacher 404s, and
independently persisted blocked-attempt audit behavior.

After authorization, the service derives an explicit roster from active
`StudentProfile` rows whose `classroom_id` is the authorized classroom. The
sorted, non-empty UUID list is passed to Stage 3's
`MatchingService.match_probe`; no institution-wide fallback exists. The same
list is stored as a UUID-array snapshot on the recognition attempt so a later
confirmation cannot select a student who was not a candidate in the original
decision. Confirmation additionally re-derives the current active roster, so
students who became inactive or left the classroom are also rejected.

## Recognition-attempt lifecycle

1. Authorize classroom/subject and derive the active roster before image work.
2. Reuse Stage 3 V4's in-memory validation and offloaded
   detect → align → embed pipeline.
3. Reuse Stage 3's candidate-scoped matcher with the server-derived UUID list.
4. Persist one `RecognitionAttendanceAttempt` containing only bounded
   identifiers, decision state, roster snapshot, confirmation state, and an
   optional attendance-record link.
5. Append a sanitized Stage 4 decision audit.
6. For `FOUND` only, validate the matched UUID is still in the authorized
   roster, then mark `PRESENT` through `AttendanceService.bulk_save`.
7. For `UNKNOWN` or `AMBIGUOUS`, return `requires_confirmation=true` and write
   no attendance.

No raw image, image path, embedding, similarity vector, provider/model path,
or raw exception is stored on an attempt or placed in Stage 4 audit metadata.

## FOUND behavior and the attendance boundary

A `FOUND` decision is the only recognition result that automatically requests
an attendance mutation. The orchestrator builds a one-row
`BulkAttendanceRequest` (`status=present`) and calls Phase 4's
`AttendanceService.bulk_save`. Consequently, Phase 4 still owns transaction,
authorization re-checking, student/classroom validation, audit, unique-key
upsert, and marked-by attribution.

No face-recognition file imports `AttendanceRepository` or `AttendanceRecord`.
The structural regression suite proves that only
`recognition_attendance_service.py` imports `AttendanceService`, and that it
invokes `bulk_save`.

Retries cannot create duplicate attendance state: Phase 4's existing upsert and
database unique constraint remain authoritative. Each persisted attempt links
the resulting attendance-record UUID after a successful mark.

## UNKNOWN / AMBIGUOUS confirmation

Neither initial status writes attendance. Confirmation requires a persisted
attempt ID plus an explicitly selected `student_profile_id` and then:

- locks the attempt row;
- re-checks authorization for its classroom/subject;
- permits only `UNKNOWN` or `AMBIGUOUS`;
- requires the selected UUID in both the original roster snapshot and current
  active classroom roster;
- calls `AttendanceService.bulk_save` in its own service-owned session while
  the attempt lock serializes concurrent confirmations;
- persists confirmer/time/attendance-record linkage and a sanitized success
  audit.

Repeating the same completed confirmation returns the same attendance-record
UUID without another attendance call or confirmation audit. Selecting a
different student after completion is rejected. If a process stops after the
attendance transaction but before attempt finalization, retry is safe because
`AttendanceService` upserts the same unique attendance key.

## Persistence and migration

Exactly one migration was added:

- revision: `4f8c1a6e92b7`
- parent: `d22bce264ecd` (the locked Stage 3 head)
- table: `recognition_attendance_attempts`
- enum: `recognition_attendance_decision` (`found`, `unknown`, `ambiguous`)

The model uses UUIDs and existing timezone-aware timestamp conventions.
Database checks enforce a positive/non-empty roster, roster-count consistency,
FOUND/matched-student consistency, and all-or-none manual-confirmation fields.
No previous migration was modified.

## Audit behavior

Stage 4 uses the Phase 4 `AuditLog`/`AuditLogRepository` infrastructure.

- successful decision: `face_recognition.attendance_decision`, with attempt
  ID, decision, matched student ID or null, and candidate count;
- successful manual confirmation:
  `face_recognition.attendance_confirmation`, with attempt ID, original
  decision, and confirmed student ID;
- blocked authorization: existing concealed Phase 4 blocked-scope audit, using
  the Stage 4 attempted action;
- invalid confirmation and invalid/empty roster outcomes: independently
  persisted `BLOCKED` audit with bounded identifiers and a safe reason code.

Tests assert the Stage 4 metadata key sets and reject biometric/image/model
path/traceback/secret-shaped content.

## Files added

- `backend_v2/alembic/versions/20260816_1200_4f8c1a6e92b7_create_recognition_attendance_attempts.py`
- `backend_v2/app/modules/face_recognition/recognition_attendance_service.py`
- `backend_v2/app/tests/phase5_stage4_helpers.py`
- `backend_v2/app/tests/test_migrations_phase5_stage4.py`
- `backend_v2/app/tests/test_phase5_stage4_architecture.py`
- `backend_v2/app/tests/test_phase5_stage4_recognition_attendance.py`
- `backend_v2/app/tests/test_phase5_stage4_service_unit.py`
- `docs/HANDOVER_PHASE_5_STAGE_4.md`

## Files modified

- `backend_v2/app/db/models.py`
- `backend_v2/app/modules/face_recognition/__init__.py`
- `backend_v2/app/modules/face_recognition/errors.py`
- `backend_v2/app/modules/face_recognition/models.py`
- `backend_v2/app/modules/face_recognition/repository.py`
- `backend_v2/app/modules/face_recognition/router.py`
- `backend_v2/app/modules/face_recognition/schemas.py`
- `backend_v2/app/tests/conftest.py`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md`

## Verification actually run

Final PostgreSQL verification completed on 2026-08-16 with Docker Desktop
4.83.0 / Engine 29.6.2 and the repository's isolated `postgres_test`
`postgres:16-alpine` service. The service was healthy on the test-only
localhost port 5433, used an ephemeral `tmpfs`, and was separate from the
production/development `postgres` service, which was never started or used.

A fresh `backend_v2_test` image build exposed unrelated historical Dockerfile
debt: `dlib` fell back to a source build in `python:3.12-slim`, but CMake is not
installed. The Dockerfile was not changed. Verification therefore used a
locally cached image of the repository's same test target, extended only in a
disposable Docker image with the current Pillow/NumPy/headless-OpenCV wheels;
the current `backend_v2` tree was bind-mounted read-only and all database work
still targeted the Compose `postgres_test` service.

The first real PostgreSQL migration run demonstrated one genuine Category-A
Stage 4 defect: three explicit foreign-key and three explicit check-constraint
names exceeded PostgreSQL's 63-character identifier limit. The minimal fix
marks those convention-generated names with Alembic `op.f(...)`, allowing
SQLAlchemy's deterministic PostgreSQL truncation. The migration round-trip
test now also asserts every Stage 4 constraint/index identifier fits the
server's configured limit.

- Full Alembic chain from empty: **passed** after the correction, through
  `98161483914f -> 6eeb9420bf8b -> 32819e0a6027 -> e1208296dad5 ->
  ca8e748dc8f2 -> d22bce264ecd -> 4f8c1a6e92b7`.
- Final `alembic current`: **`4f8c1a6e92b7 (head)`**.
- Stage 4 migration round-trip test: **1 passed, 0 skipped**. It executed
  `d22bce264ecd -> 4f8c1a6e92b7 -> d22bce264ecd -> 4f8c1a6e92b7`.
- Five Stage 4 PostgreSQL integration tests: **4 passed, 1 failed, 0 skipped**.
  All five executed. FOUND marking/upsert idempotency, server-derived active
  roster, UNKNOWN explicit-confirmation idempotency, AMBIGUOUS no-auto-write,
  cross-classroom rejection, and persisted decision/confirmation/blocked audit
  rows passed. The unrelated-teacher case verified concealed 404, no inference,
  and no attendance, then hit the explicitly out-of-scope Stage 2
  `MissingGreenlet` while dereferencing a commit-expired actor UUID for its
  final audit query; this is Category B, not a Stage 4 behavior failure.
- Relevant Phase 4 `AttendanceService`: **24 passed**.
- Relevant Stage 3 matcher/image-validation/offload/audit batch: **38 passed,
  6 failed**; all six failures are Category B setup failures through the known
  Stage 2 upload/serialization `MissingGreenlet` path. No test skipped.
- Complete backend pytest suite, run once: **625 passed, 47 failed, 0 skipped,
  13 warnings**. Strict classification: **A=0, B=45, C=2**. Category C is the
  historical Phase 4 migration test's stale expectation that `upgrade head`
  remains `e1208296dad5`, plus the independent historical Stage 2 test that
  expects HTTP 409 while allowing the service's `ENROLLMENT_NOT_FOUND` code,
  which is defined as HTTP 404. No B or C defect was changed.
- `python -m compileall -q app alembic`: **passed**.
- Ruff check on all 15 changed Stage 4 Python files: **passed**.
- Ruff format check on all 15 changed Stage 4 Python files: **passed**.
- Real-model smoke test: **not run**. No YuNet/dlib model artifact was needed,
  downloaded, or packaged for these provider-faked integration gates.

## Known out-of-scope blocker

The pre-existing Stage 2
`biometric_enrollment/service.py::create_sample` `MissingGreenlet` defect was
not modified. It accounts for Category-B failures above, including dependent
Stage 3 setup and the final audit lookup in one otherwise-completed Stage 4
case. Stage 4 DB tests continue to seed ACTIVE/PROCESSED samples with the
existing direct ORM helper pattern. This blocker remains for a later explicitly
authorized closure task.

## Boundary confirmation

- UNKNOWN and AMBIGUOUS never auto-write attendance.
- All automatic and confirmed attendance writes go only through
  `AttendanceService`.
- Authorization occurs before image validation/inference where application
  code is reached.
- Candidate scope is authorized, classroom-only, explicit, and non-empty.
- Stage 3 V4 image limits and no-global-Pillow-mutation behavior were reused,
  not reimplemented or weakened.
- Stage 5 was not started.
- Phase 6/frontend work was not started.
- No Git operation was performed.
