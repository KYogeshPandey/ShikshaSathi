# Handover — Rebuild Phase 4, Stage 2 (Attendance Service, Authorization, Audit)

**Status: Stage 2 complete for its own defined scope.** This checkpoint
delivers the transactional `AttendanceService` (bulk-save with upsert
semantics), teacher-ownership authorization with the existing
concealment convention, atomic success-audit logging, and independently
transacted blocked-audit logging. **No FastAPI routers, no CSV export,
no statistics/detail/daily endpoints, and no student self-service exist
yet** — nothing in `app/modules/attendance/` is reachable over HTTP.
This mirrors exactly how `docs/HANDOVER_PHASE_3_STAGE_2.md` scoped
Phase 3's own second checkpoint relative to its Stage 1.

## What this checkpoint actually is

Built directly on the Stage 1 baseline (`docs/HANDOVER_PHASE_4_STAGE_1.md`
— models, errors, schemas, repositories, migration `e1208296dad5`, all
unmodified here). This session's new work:

1. `app/modules/attendance/service.py` — built from scratch:
   `AttendanceService` (the transactional bulk-save/authorization
   orchestrator) and `BlockedAuditWriter` (the independent-session
   blocked-audit writer).
2. `app/modules/attendance/errors.py` — extended with Stage 2's
   authorization and batch-validation errors (see "Errors added" below).
3. `app/modules/attendance/schemas.py` — extended with
   `AttendanceBulkSaveResult`, the typed, non-echoing service result.
4. `app/tests/test_attendance_service.py` — 24 new database-backed
   service-level tests (see "Tests added" below).
5. This handover; `docs/PROGRESS.md` updated with a Phase 4 Stage 2
   section; ADR 0010 extended (not replaced) with the Stage 2 decisions
   actually implemented.

## Read first, in order

`docs/HANDOVER_PHASE_4_STAGE_1.md` → this file → `docs/PROGRESS.md`'s
"Phase 4 Stage 2" section (bottom of the file) →
`docs/adr/0010-phase4-attendance-and-audit-trail.md`'s Stage 2 addendum
→ `app/modules/attendance/service.py` itself.

## AttendanceService design

### Entry point

`AttendanceService.bulk_save(*, current_user, payload, request_id=None)`
returns `AttendanceBulkSaveResult` (`classroom_id`, `subject_id`,
`attendance_date`, `created_count`, `updated_count`, `total_count`,
`record_ids`) — deliberately **does not echo the submitted batch** (no
per-record status/remarks reflected back), per the brief's instruction A.

### Order of operations inside `bulk_save`

1. **Batch-shape defense in depth** (`_validate_batch_shape`, before any
   DB access): re-checks the 200-row cap and no-duplicate-student rule
   that `BulkAttendanceRequest` already enforces at parse time. Exists so
   the service never relies solely on an already-validated request
   object having been constructed the normal way — see "Genuine review
   findings and fixes" below for why this matters in practice.
2. **Role check**: only `admin`/`teacher` may proceed;
   `AttendanceRoleNotPermittedError` (403) otherwise. This is a
   defense-in-depth backstop for a future router's `require_roles`
   dependency, not a replacement for it.
3. **One transaction** (`service_transaction(self._session)`) wraps
   everything from here to the end of the method body: reference lookup,
   authorization, the active-reference check, student validation, the
   upsert loop, and the success-audit write.
4. **Reference lookup + authorization**:
   - **Admin**: `classroom`/`subject` must simply exist
     (`ClassroomNotFoundError`/`SubjectNotFoundError`, 404, otherwise).
   - **Teacher**: `_authorize_teacher_scope` is the *only* path — see
     "Authorization behavior" below.
5. **Active-reference check** (shared by both roles, after
   authorization): `classroom.is_active` and `subject.is_active` must
   both be true, or `InactiveAcademicReferenceError` (409, reused
   directly from `app.modules.academics.errors` rather than duplicated).
6. **Student validation** (`_validate_students`): every record's student
   must exist, be active, and belong to the target classroom — checked
   for *every* record before any attendance row is written, so an
   invalid record anywhere in the batch never leaves a partial write to
   roll back; it simply never starts.
7. **Upsert loop** (`_write_attendance_records`): for each record, look
   up the existing row by the (student, classroom, subject, date)
   unique key; create if absent, update in place if present.
   `marked_by_user_id` is set from `current_user.id` on every write —
   never from any client-supplied field (no such field exists on
   `BulkAttendanceRecordIn`/`BulkAttendanceRequest` at all).
8. **Success-audit write** (`_write_success_audit`), still inside the
   same transaction — see "Successful audit atomicity" below.
9. Transaction commits; the typed result is built and returned.

Any exception anywhere in steps 4–8 propagates out of the `async with
service_transaction(...)` block, which rolls back every attendance write
(and the audit write, if it got that far) made during this call.

## Authorization behavior

`_authorize_teacher_scope` is the single method that decides whether a
teacher may act on a given `(classroom_id, subject_id)`. Every distinct
denial reason funnels into the **same** client-visible error,
`AttendanceScopeNotFoundError` (404):

- teacher profile missing or inactive,
- classroom and/or subject does not exist,
- teacher assignment for that exact (teacher, classroom, subject) triple
  is missing or inactive (`TeacherAssignmentRepository.exists(...,
  active_only=True)`).

This is the existing concealment convention already established in
`app.modules.auth.authorization` (an unrelated/denied object looks
identical to a genuinely missing one) — a malicious or mistaken teacher
client cannot distinguish "that classroom doesn't exist" from "you're
just not assigned to it." The **real** reason is recorded server-side
only, as a safe `reason_code` string constant in the blocked audit row's
`event_metadata` — never in the exception raised to the caller.

Once authorized, the teacher path rejoins the same active-reference
check as the admin path (step 5 above) — so a teacher with a valid,
active assignment to a classroom that was *later* deactivated by an
admin still gets a clear `InactiveAcademicReferenceError`, not a
concealed 404 (this is a legitimate business-rule rejection, not an
ownership leak, since the teacher already knows their own assignments).

## Transaction ownership

Two independent transaction boundaries, never mixed:

1. **Main batch transaction** — `service_transaction(self._session)`,
   bound to the caller's own request-scoped session. Covers reference
   lookup, authorization reads, the upsert loop, and the success-audit
   write. Repositories never call `commit()` themselves (verified in the
   review below) — only `flush()`/`refresh()` — so this is the only
   commit point for a successful batch.
2. **Blocked-audit transaction** — `BlockedAuditWriter`, a brand-new
   `AsyncSession` built from `async_sessionmaker(bind=get_engine(settings))`
   — the same shared, cached engine (keyed by `Settings.DATABASE_URL`)
   every other part of the application uses, not an ad hoc or
   differently-configured connection. Opens, writes one row, commits,
   and closes — entirely independent of whatever happens to the main
   session's transaction afterward (which, in Stage 2, hasn't been
   written to at all yet when a blocked scope is detected).

## Successful audit atomicity

`_write_success_audit` runs inside the same `service_transaction` block
as the attendance writes, using `self._audit_logs` (bound to the same
session). Consequences, all deliberate:

- If the success-audit `create()` call itself fails, that exception
  propagates out of the `async with` block exactly like any other
  mid-batch failure — every attendance write made earlier in the same
  call rolls back with it. Verified by
  `test_failed_success_audit_insertion_rolls_back_all_attendance_writes`.
- If an attendance write fails first, the success-audit write is never
  reached at all. Verified by
  `test_failed_attendance_transaction_creates_no_success_audit`.
- A successful batch produces **exactly one** success audit row (not one
  per attendance record). Verified by
  `test_successful_batch_creates_exactly_one_success_audit`.
- `event_metadata` is bounded and sanitized:
  `attendance_date`, `created_count`, `updated_count`, `total_count`,
  `record_ids` (stringified, truncated to the first 50), and
  `record_ids_truncated`. No raw remarks, request body, token, cookie,
  password, or stack trace ever enters it — verified by
  `test_success_audit_metadata_is_bounded_and_safe`, which plants a
  distinctive remarks string and asserts it is absent from the stored
  metadata.

## Blocked-audit independent transaction

`BlockedAuditWriter.write(...)` is called from
`_authorize_teacher_scope` before the concealed error is raised. Its
metadata is deliberately minimal: `reason_code` (one of three safe,
non-identifying constants) and `attempted_action`. `classroom_id`,
`subject_id`, `request_id`, `actor_user_id`, `action`, and `outcome` are
all top-level `AuditLog` columns already carried by
`AuditLogRepository.create`, not duplicated into the metadata blob.

**Genuine review finding, fixed this session:** the first draft of this
method let an exception from the blocked-audit write itself propagate
directly out of `_authorize_teacher_scope`, which would have replaced
the intended `AttendanceScopeNotFoundError` with whatever the audit
write failed with (e.g. a raw `IntegrityError`) — silently changing the
client-visible error and its status code depending on an unrelated,
independent write's success. Fixed by wrapping the write in a narrow,
documented `try/except Exception` (mirroring the one already-accepted
broad-exception idiom in `app/db/session.py`'s
`require_database_ready`): on failure, only `type(exc).__name__` is
logged (never the message, matching the project's no-raw-exception-text
rule), and `AttendanceScopeNotFoundError` is still raised afterward
either way. The broad-exception scan below reports this one match
correctly — it is not treated as zero.

## Genuine review findings and fixes (Priority 1)

Two real issues were found and fixed in this session's review pass; both
are described in more detail above:

1. **Blocked-audit-write failure could replace the ownership error** —
   fixed with the `try/except Exception` wrapper described above.
2. **A bare `assert classroom is not None` / `assert subject is not
   None` guarded a genuine runtime invariant** (not client input) after
   authorization succeeds. `assert` statements are stripped under
   `python -O`, which would silently remove this safety net in an
   optimized deployment. Replaced with an explicit `if ... is None: raise
   RuntimeError(...)` check that cannot be compiled away.

Everything else checked against the Priority 1 list was already correct
and required no change: imports resolve (see the scan below); no
repository calls `commit()`; `bulk_save` uses exactly one
`service_transaction`; the success audit is written inside that same
transaction; the blocked audit uses a fully independent
session/transaction bound to the shared cached engine (not an ad hoc
one); there is no nested-transaction misuse; no ORM relationship is
lazy-loaded anywhere in the new code (every cross-table read is an
explicit `get_by_id`/`get_by_user_id`/`exists` call); audit metadata (both
success and blocked) never contains raw remarks, tokens, cookies,
passwords, request payloads, or exception strings; classroom, subject,
teacher profile, assignment, and student activity are all checked;
duplicate-student and batch-size limits are enforced at both the schema
layer (Stage 1) and the service layer (Stage 2, defense in depth); and
`marked_by_user_id`/the authorizing actor are always taken from
`current_user`, never from any client-supplied field.

## Errors added (`app/modules/attendance/errors.py`)

| Error | HTTP | Raised when |
|---|---|---|
| `AttendanceBatchTooLargeError` | 422 | Service-level re-check of the 200-row cap (defense in depth) |
| `AttendanceDuplicateStudentInBatchError` | 422 | Service-level re-check of no-duplicate-student (defense in depth) |
| `AttendanceRoleNotPermittedError` | 403 | Caller's role is neither admin nor teacher |
| `AttendanceScopeNotFoundError` | 404 | Any teacher-scope denial (concealed, see above) |
| `AttendanceStudentNotFoundError` | 422 | A record's `student_profile_id` does not exist |
| `AttendanceInactiveStudentError` | 422 | A record's student profile is inactive |
| `AttendanceStudentNotInClassroomError` | 422 | A record's student does not belong to the target classroom |

`ClassroomNotFoundError`, `SubjectNotFoundError`, and
`InactiveAcademicReferenceError` are reused directly from
`app.modules.academics.errors` rather than duplicated, per the brief's
"do not duplicate ... unnecessarily" instruction.

## Files created/modified

**Created:**
- `app/modules/attendance/service.py`
- `app/tests/test_attendance_service.py`
- `docs/HANDOVER_PHASE_4_STAGE_2.md` (this file)

**Modified:**
- `app/modules/attendance/errors.py` — Stage 2 errors appended; Stage 1
  errors untouched.
- `app/modules/attendance/schemas.py` — `AttendanceBulkSaveResult` added;
  Stage 1 schemas untouched.
- `docs/PROGRESS.md` — Phase 4 Stage 2 section appended; all historical
  sections preserved verbatim.
- `docs/adr/0010-phase4-attendance-and-audit-trail.md` — Stage 2 addendum
  appended for the decisions actually implemented this session (batch-
  level success audit, bounded sanitized metadata, independent
  blocked-audit transaction, concealed unrelated-teacher-scope,
  authenticated-actor ownership). Stage 1's decisions are unedited.

**Not touched:** any Stage 1 file in `app/modules/attendance/models.py`,
`repository.py`; migration `e1208296dad5`; `app/db/models.py`;
`alembic/env.py`; anything under legacy `backend/`/`frontend/`.

## Tests added (`app/tests/test_attendance_service.py`, 24 tests)

Database-backed, using the `db_session` fixture (same skip-if-unreachable
convention as every prior Phase 3/4 repository test). Covers, in order:
admin bulk-save success; assigned-teacher success; unrelated teacher
rejected (concealed); blocked attempt persists exactly one blocked audit;
blocked audit's expected fields (actor, request_id, action, outcome,
classroom, subject, reason code); blocked audit metadata has no
secrets/payload; inactive teacher profile rejected; inactive assignment
rejected; inactive classroom rejected; inactive subject rejected;
inactive student rejected; student outside target classroom rejected;
duplicate student IDs rejected before any write (via
`BulkAttendanceRequest.model_construct` bypassing the schema's own
validator, to genuinely exercise the service-level defense); batch >200
rejected (same bypass technique); new rows created; existing rows
updated in place (same `record_ids` across two calls); `marked_by_user_id`
sourced from the authenticated caller; forced repository failure midway
rolls back the complete batch (via `monkeypatch` on the repository
instance — a real, deterministic failure-injection technique, not a fake
assertion); an invalid later student leaves zero partial writes; failed
success-audit insertion rolls back all attendance writes; a failed
attendance transaction creates no success audit; a successful batch
creates exactly one success audit; success-audit metadata is bounded and
contains no remarks/tokens/passwords/raw payload; and a student-role
caller is rejected by `bulk_save` directly.

## Checks actually executed this session

- `python -m compileall -q app alembic scripts` — passed, 0 syntax errors
  across the whole tree, including every new/modified file.
- Custom AST-based internal `app.*` import-resolution scan (module-level)
  — 389/389 `app.*` imports resolved to an existing module across the
  whole tree.
- A second, stricter AST scan specifically for this session's new/
  modified files (`service.py`, `test_attendance_service.py`): every
  individual imported *name* (not just the module) was checked against
  that module's actual top-level definitions — 0 problems found across
  every `from app... import ...` statement in both files.
- Model-registration / migration-table-name diff — 12/12 tables still
  match exactly in both directions (Stage 2 adds no new tables, so this
  is an unchanged-invariant check, not new ground).
- Trailing-whitespace scan on all new/modified files — 0 matches.
- Line-length scan (100-char Ruff config) on all new/modified files — 0
  lines over, after wrapping 19 lines in the new test file during
  authoring (re-verified after the fix).
- Broad-exception scan (`except Exception`/bare `except:`) — **1 match**,
  in `service.py`'s `_authorize_teacher_scope` — this is the single,
  deliberate, documented fix described above (mirrors the one
  already-accepted instance of this idiom in `app/db/session.py`). Not
  reported as zero, since it is a genuine, intentional exception.
- TODO/FIXME/`NotImplementedError`/fake-assertion (`assert True`) scan —
  0 matches.
- Secret/debug-print scan — 0 genuine matches. The scan does flag the
  test file's `_PASSWORD = "a-strong-real-password-1"` constant (an
  established test-only convention already used identically in
  `test_attendance_repository.py`/`test_academics_repository.py`, not a
  real credential) and the deliberate literal string
  `"TOP-SECRET-REMARK-VALUE"` used *as test input* specifically to prove
  it does **not** leak into audit metadata — both are expected, reviewed,
  and not genuine secrets.

## Checks unavailable in this sandbox — same historical limitation

`pip install` of any package (`fastapi`, `sqlalchemy`, `asyncpg`,
`alembic`, `pytest`, `pytest-asyncio`, `httpx`, `structlog`, etc.) is
confirmed blocked (no network egress), consistent with every prior
Phase 3/4 checkpoint in this sandbox. As a direct consequence:

- No `pytest` collection or run was possible — the 24 new tests are
  syntactically valid (verified by `compileall` and the import-resolution
  scans above) and structurally consistent with the already-passing
  Stage 1 repository tests' fixture conventions, but are **not
  runtime-verified** in this session.
- `ruff format --check .` / `ruff check .` — unavailable, `ruff` not
  installed.
- `mypy app` — unavailable, `mypy` not installed.
- `docker compose ...` — unavailable, Docker itself is not present.

No check above is claimed to have passed where it did not actually run.
Where full execution wasn't possible, the closest available static/
structural verification was performed instead and is never conflated
with the runtime check it stands in for.

**The repository owner should run the full Docker gate before trusting
this checkpoint's runtime behavior:**

```bash
docker compose --profile test build backend_v2_test
docker compose --profile test run --rm backend_v2_test
```

Expected: all 24 new service tests pass, all Stage 1 tests still pass
unmodified, Ruff format/lint pass, and mypy passes. Any failure should be
fixed before Stage 3 begins.

## Must NOT be redone

- Do not regenerate or restart any Phase 1-3 module, or Stage 1's models/
  repository/migration.
- Do not edit migration `e1208296dad5` or any earlier migration.
- Do not add routers, CSV export, statistics/detail/daily endpoints, or
  student self-service — all Stage 3.

## Exact Stage 3 starting point

Per `docs/IMPLEMENTATION_PLAN.md` Phase 4 and the Stage 2 brief's own
"Do not begin" list, Stage 3 is:

1. **FastAPI routers** for `AttendanceService.bulk_save` (admin + teacher,
   behind `require_roles(UserRole.ADMIN, UserRole.TEACHER)` — the router
   is where the 403 for a wrong-role caller actually gets enforced at the
   HTTP boundary; `AttendanceRoleNotPermittedError` in the service is a
   defense-in-depth backstop behind it, not a replacement for it) and
   for audit-log reads (admin-only).
2. **Statistics/detail/daily endpoints**, built on
   `AttendanceRepository.aggregate_counts`/`list`/`count` (already
   delivered in Stage 1, unused until now).
3. **CSV export.**
4. **Student self-service** (`/attendance/mystats`-equivalent), deriving
   identity from the JWT the same way the legacy app's one correct
   endpoint did (`docs/AUDIT.md` §2.4 positive finding).
5. A router-level `request_id` needs to be threaded into
   `AttendanceService.bulk_save`'s `request_id` parameter from
   `request.state.request_id` (already set by existing middleware,
   `app/core/middleware.py`) — the service already accepts and uses it,
   nothing in the service needs to change for this.

See `docs/IMPLEMENTATION_PLAN.md` Phase 4's full acceptance criteria,
unchanged by this Stage 2 checkpoint, for the complete list.
