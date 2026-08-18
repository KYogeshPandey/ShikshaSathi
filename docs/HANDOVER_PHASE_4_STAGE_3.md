# Handover — Rebuild Phase 4, Stage 3 (Attendance Reads, Statistics, CSV Export, Audit-Log API)

**Status: Stage 3 source and tests are complete for their own defined
scope. Runtime PostgreSQL/pytest verification is pending** — the exact
same limitation recorded in every Phase 3/4 checkpoint so far. This
checkpoint delivers everything that was reachable only through direct
service/repository calls in Stage 2 as real, authorized HTTP endpoints:
attendance detail/daily/statistics reads, CSV export, student
self-service, and an admin-only audit-log read API. Nothing in this
checkpoint touches Phase 5 (face recognition) or begins Stage 4.

## What this checkpoint actually is

Built directly on the Stage 1 baseline (`docs/HANDOVER_PHASE_4_STAGE_1.md`
— models, errors, schemas, repositories, migration `e1208296dad5`) and
the Stage 2 baseline (`docs/HANDOVER_PHASE_4_STAGE_2.md` —
`AttendanceService.bulk_save`, `BlockedAuditWriter`, the concealed
teacher-ownership convention). Neither is modified in this stage except
where explicitly noted below. This session's new work:

1. `app/modules/attendance/repository.py` — extended (not replaced):
   an optional `status` filter added to `_apply_filters`/`list`/`count`/
   `aggregate_counts`; `list_daily` (exact classroom/subject/date scope);
   `aggregate_by_student`/`aggregate_by_classroom` (single `GROUP BY ...
   FILTER (WHERE ...)` queries, the same aggregation technique Stage 1's
   `aggregate_counts` already used); `list_for_export` (joins
   `StudentProfile` for `roll_number` only). Three new typed dataclasses
   (`StudentAttendanceAggregate`, `ClassroomAttendanceAggregate`,
   `AttendanceExportRow`) so no raw SQLAlchemy `Row` ever reaches a
   service or router.
2. `app/modules/attendance/schemas.py` — extended with the Stage 3
   response shapes: `AttendanceStatsGrouping`, `DailyAttendanceResponse`,
   `AttendanceStatsOverall`/`AttendanceStatsByStudent`/
   `AttendanceStatsByClassroom`/`AttendanceStatsResponse`,
   `StudentSelfStatsResponse`.
3. `app/modules/attendance/read_service.py` — new. `AttendanceReadService`:
   one shared `authorize_scope` method (plus its private
   `_authorize_teacher_scope` helper) used by every general read/export
   endpoint, and `get_detail`/`get_daily`/`get_stats`/`export`/
   `get_self_detail`/`get_self_stats`. Does not call or modify Stage 2's
   private `AttendanceService._authorize_teacher_scope` — see "Genuine
   design decisions" below for why.
4. `app/modules/attendance/csv_export.py` — new. `build_attendance_csv`/
   `build_export_filename`, plus the formula-injection escape helper.
5. `app/modules/attendance/router.py` — new. `POST /attendance/bulk`,
   `GET /attendance/detail`, `GET /attendance/daily`,
   `GET /attendance/stats`, `GET /attendance/export`,
   `GET /attendance/me/detail`, `GET /attendance/me/stats`.
6. `app/modules/attendance/audit_router.py` — new.
   `GET /audit-logs`, `GET /audit-logs/{audit_log_id}` — admin-only,
   read-only, calling `AuditLogRepository` directly (no extra service
   layer — see "Genuine design decisions").
7. `app/api/router.py` — both new routers registered exactly once.
8. `app/tests/attendance_http_helpers.py` — new shared seed helper
   (reuses `phase3_http_helpers.seed_user`/`auth_headers`/
   `create_resource` as-is).
9. Four new HTTP test files (see "Tests added").
10. This handover; `docs/PROGRESS.md` appended with a Phase 4 Stage 3
    section; ADR 0010 extended (not replaced) with the Stage 3 decisions
    actually implemented; `backend_v2/README.md` updated with the full
    Phase 4 endpoint inventory.

## Read first, in order

`docs/HANDOVER_PHASE_4_STAGE_2.md` → this file → `docs/PROGRESS.md`'s
"Phase 4 Stage 3" section (bottom of the file) →
`docs/adr/0010-phase4-attendance-and-audit-trail.md`'s Stage 3 addendum
→ `app/modules/attendance/read_service.py` itself.

## Attendance endpoint inventory

All under `API_V1_PREFIX` (`/api/v1`), all requiring
`Authorization: Bearer <access_token>`:

| Method | Path | Role/scope | Notes |
|---|---|---|---|
| POST | `/attendance/bulk` | admin; assigned teacher | Stage 2's `bulk_save`, now wired to HTTP. `actor`/`marked_by` are never client-supplied fields. |
| GET | `/attendance/detail` | admin; assigned teacher | `classroom_id`/`subject_id` required; `student_profile_id`/`date_from`/`date_to`/`status`/`limit`/`offset` optional. |
| GET | `/attendance/daily` | admin; assigned teacher | `classroom_id`/`subject_id`/`attendance_date` all required. Empty scope → `records: []`. |
| GET | `/attendance/stats` | admin; assigned teacher | `grouping` = `overall` (default) / `student` / `classroom`. |
| GET | `/attendance/export` | admin; assigned teacher | In-memory CSV, same filters as `/detail`. |
| GET | `/attendance/me/detail` | student only | No `student_profile_id` parameter exists on this route. |
| GET | `/attendance/me/stats` | student only | Own overall statistics only. |

## Audit-log endpoint inventory

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/audit-logs` | admin only | Filters: `actor_user_id`, `action`, `outcome`, `entity_type`, `classroom_id`, `subject_id`, `date_from`, `date_to`, `limit`, `offset`. |
| GET | `/audit-logs/{audit_log_id}` | admin only | Missing: `404`. |

No `POST`/`PUT`/`PATCH`/`DELETE` route exists for `/audit-logs` anywhere
— confirmed by this session's duplicate/route-inventory scan (see
"Checks actually run"). This matches `AuditLogRepository`'s structural
shape: it has no `update`/`delete` method to call even by mistake.

## Authorization matrix

| Role | Bulk | Detail/Daily/Stats/Export | Self-service (`/me/*`) | Audit logs |
|---|---|---|---|---|
| Admin | ✅ (active scope only) | ✅ (active scope only) | ❌ (403) | ✅ |
| Teacher | ✅ if actively assigned to exact classroom+subject | ✅ if actively assigned to exact classroom+subject | ❌ (403) | ❌ (403) |
| Student | ❌ (403) | ❌ (403) | ✅ own records only | ❌ (403) |
| Unauthenticated / inactive | ❌ (401) | ❌ (401) | ❌ (401) | ❌ (401) |

## Teacher read-scope authorization (genuine design decision)

Every general read/export endpoint — detail, daily, stats, export —
calls **one** method, `AttendanceReadService.authorize_scope`, so
authorization logic is never duplicated per route. It deliberately
mirrors Stage 2's `bulk_save` write-scope shape exactly, rather than
inventing a looser "reads are safer than writes" rule:

- **Admin**: classroom/subject must exist (`ClassroomNotFoundError`/
  `SubjectNotFoundError`, `404`) and both must be **active**
  (`InactiveAcademicReferenceError`, `409`). Admin reads only active
  attendance scopes — the same restriction as the write path, not a
  broader "admin sees everything" carve-out.
- **Teacher**: active `TeacherProfile` + an active `TeacherAssignment`
  matching the exact `(classroom_id, subject_id)` pair. Any denial
  reason (missing/inactive profile, non-existent classroom/subject,
  missing/inactive assignment) is concealed as the same
  `AttendanceScopeNotFoundError` (`404`) — never distinguished in the
  response.

**This module does not call or modify Stage 2's private
`AttendanceService._authorize_teacher_scope`.** That method belongs to
`AttendanceService` and is reserved for `bulk_save`'s write path per
Stage 2's "Must NOT be redone" list. `AttendanceReadService` has its own
`_authorize_teacher_scope`, structurally similar (same concealment
outcome, same three reason codes) but a distinct implementation and
distinct, Stage-3-only reason-code constants
(`_REASON_TEACHER_PROFILE_INACTIVE_OR_MISSING`,
`_REASON_CLASSROOM_OR_SUBJECT_NOT_FOUND`,
`_REASON_ASSIGNMENT_INACTIVE_OR_MISSING`). This was a deliberate
trade-off: a small amount of structural duplication between two
private methods in two different classes, in exchange for never
touching Stage 2's already-reviewed, already-tested `service.py` for an
unrelated (read-side) concern. Every read/export router endpoint still
calls only this one Stage 3 method — the "do not duplicate
authorization per endpoint" requirement is satisfied at this module's
boundary.

`classroom_id`/`subject_id` are **required** (non-optional) query
parameters on every general read/export endpoint, for both admin and
teacher. This was necessary to reuse the same exact-scope authorization
shape for both roles uniformly, and it keeps "no dashboard/leaderboard"
honestly enforced — every request is one exact scope, never an
unbounded cross-classroom rollup.

## Blocked detail/daily/stats/export audit behavior

Identical mechanism to Stage 2's blocked bulk-save audit, reused
as-is (`app.modules.attendance.service.BlockedAuditWriter` — not
reimplemented): one `AuditLog` row per denied attempt, written in its
own independent session/transaction (never the caller's), with
`outcome=blocked`, the real `request_id`, and a safe `reason_code` in
`event_metadata` — never the raw exception, the request body, or
remarks. A write failure of the blocked-audit row itself is logged
(exception *type* only) but never replaces or suppresses the original
`AttendanceScopeNotFoundError` raised to the client — the exact same
`try/except Exception` convention Stage 2 established, applied here to
four new action strings: `attendance.read_detail`,
`attendance.read_daily`, `attendance.read_stats`, `attendance.export`.

No success audit is written for reads or exports — only `bulk_save`
writes a success audit row. Neither Stage 3 brief asked for a success
audit on every read, and adding one would make read-heavy traffic the
dominant audit-log write source for no stated benefit.

## Student self-service behavior

`AttendanceReadService._resolve_own_student_profile` derives the caller's
`StudentProfile` from `current_user.id` — never from a client-supplied
ID. Neither `/attendance/me/detail` nor `/attendance/me/stats` has a
`student_profile_id` parameter on its function signature at all (not
"ignored if present" — it simply is not part of the route's contract).
A missing or inactive own profile raises `StudentProfileNotFoundError`
(`404`) — the same self-profile error convention already established in
`app.modules.profiles.student_service.StudentProfileService.get_for_user`,
not a new error type invented for attendance. A defense-in-depth role
check (`AttendanceRoleNotPermittedError`, `403`) exists behind the
router's own `require_roles(UserRole.STUDENT)`, mirroring Stage 2's same
belt-and-suspenders pattern for `bulk_save`.

## Statistics behavior

- `attendance_percentage = round(present_count / total_count * 100, 2)`.
- **Zero matching records → `0.0`**, defined explicitly (not a division
  error, not `null`).
- `present_count + absent_count` always equals `total_count` (both are
  `FILTER (WHERE ...)` aggregates over the same row set as `total_count`
  itself — structurally guaranteed, not just tested).
- Three grouping modes: `overall` (default), `student`, `classroom` —
  each backed by exactly one SQL aggregation query
  (`aggregate_counts`/`aggregate_by_student`/`aggregate_by_classroom`),
  never an in-Python loop over individual attendance rows.
- No ranking, defaulter classification, leaderboard, trend, or
  prediction — explicitly Phase 8 scope, not touched here.

## CSV generation and formula-injection protection

`app/modules/attendance/csv_export.py` builds the entire document in a
single in-memory `io.StringIO` buffer via the standard-library `csv`
module — no temporary file is ever created. Fixed column order:
`attendance_date`, `classroom_code`, `subject_code`,
`student_profile_id`, `student_roll_number`, `status`, `remarks`,
`marked_by_user_id`, `created_at`, `updated_at`. `classroom_code`/
`subject_code` come from the already-authorized `Classroom`/`Subject`
objects (constant for one export request, since `classroom_id`/
`subject_id` are required exact-scope filters) — not re-joined per row.
An empty result still returns a valid CSV containing only the header
row. The filename (`attendance-<classroom_code>-<subject_code>.csv`) is
built exclusively from those same already-authorized codes, with any
character outside `[A-Za-z0-9_-]` defensively replaced by `_` — never
from client input.

**Formula-injection protection**: any text cell beginning with `=`,
`+`, `-`, or `@` is prefixed with a single leading apostrophe (`'`)
before being written — applied to `remarks` (the genuinely free-text
field) and, defensively, to `student_roll_number` (admin-entered, not
currently constrained to a strict character set). This is the standard,
widely-supported spreadsheet convention for forcing literal-text
interpretation; the apostrophe itself is not displayed on open.

## Audit-log admin-only read behavior

`audit_router.py` calls `AuditLogRepository` (Stage 1, unmodified)
directly — no extra service-layer indirection, since there is no
scope-authorization rule beyond "caller's role is admin" (already
enforced by the router's own `require_roles(UserRole.ADMIN)`
dependency). `AuditLogRepository` has no `update`/`delete` method to
call even by mistake, so the append-only guarantee is structural, not
just a routing convention.

## Genuine design decisions made this session

1. **`classroom_id`/`subject_id` required, not optional, on every
   general read/export endpoint.** Covered above under "Teacher
   read-scope authorization" — necessary to reuse one authorization
   shape for both roles and to keep statistics from becoming an
   unbounded, Phase-8-style rollup.
2. **A fresh `_authorize_teacher_scope` in `read_service.py`, not a call
   into Stage 2's private method.** Covered above.
3. **`AttendanceStatsResponse` is one schema for all three grouping
   modes** (`overall`/`by_student`/`by_classroom`, exactly one populated
   per response), rather than three separate response models/routes.
   Keeps the router's `response_model` declaration and the OpenAPI
   surface simpler while every field remains fully typed.
4. **No success audit for reads/exports.** Covered above under "Blocked
   detail/daily/stats/export audit behavior."
5. **Admin's read scope is restricted to active classrooms/subjects**,
   the same as the write path — not a broader "admin bypasses the
   active check" allowance. Chosen for authorization symmetry between
   read and write, and because "may read active attendance scopes" is
   explicit in the Stage 3 brief's own wording for admin.

## Tests added

Four new HTTP test files (`app/tests/`), all using the real
router → `AttendanceReadService`/`AttendanceService` → repository →
Postgres path via `client_db`/`db_session`
(`ASGITransport`, matching every prior phase's convention):

- **`test_attendance_http.py`** — bulk-save (unauthenticated/inactive/
  student → 401/401/403; admin and assigned-teacher success; unrelated
  teacher concealed 404 + blocked audit; request-ID reaching the success
  audit; `marked_by_user_id`/`actor_user_id` rejected as unknown fields
  via the schema's own `extra="forbid"`); detail (admin/teacher success,
  unrelated-teacher denial + audit, deterministic pagination, classroom/
  subject/student/status/date filtering, invalid date range → 422);
  daily (exact scope, empty-scope typed empty result); student
  self-service (own detail/stats, no `student_profile_id` parameter,
  cross-student isolation, inactive/missing profile → 404,
  teacher/admin denied → 403).
- **`test_attendance_stats_http.py`** — overall/student-grouped/
  classroom-grouped counts, zero-rows → `0.0`, 2-decimal rounding
  (`1/3` → `33.33`), date-range filtering, `present + absent == total`,
  unrelated-teacher denial + audit.
- **`test_attendance_csv_http.py`** — admin/teacher export, unrelated-
  teacher denial + audit, student forbidden, `Content-Type`/
  `Content-Disposition`, stable column order, filters affecting rows,
  empty-result header-only CSV, all four formula-injection trigger
  characters (`=`, `+`, `-`, `@`) escaped, no-temporary-file check
  (directory-listing diff on the OS temp dir), no-sensitive-data check
  (bearer token / "password" / "authorization" absent from the CSV body).
- **`test_audit_log_http.py`** — admin list/detail success, teacher/
  student → 403, filtering + pagination, missing ID → 404, both a
  success audit (from bulk-save) and a blocked audit (from a denied
  read) visible, no `POST`/`PUT`/`PATCH`/`DELETE` route exists (405),
  no sensitive data in the response body.

Does not duplicate Stage 2's 24 service-level tests
(`test_attendance_service.py`, unmodified) — only the HTTP-layer
concerns Stage 3 adds.

## Checks actually run this session

- `python -m compileall -q app alembic scripts` — passed, 0 syntax
  errors across the whole tree, including every Stage 3 file.
- Custom AST-based internal `app.*` import-resolution scan, run twice
  (once for the core Stage 3 modules, once again including the four new
  test files and the shared test helper) — 110/110 imported names
  resolved to an actual top-level definition in their target module; 0
  problems both times.
- Duplicate HTTP method/path scan across the **entire** app (55 routes
  total after Stage 3's additions) — 0 duplicates, confirmed with each
  route's full prefixed path, not just its route-local path.
- Repository/service/router signature-consistency scan — every keyword
  argument `router.py`/`audit_router.py` passes into
  `AttendanceReadService`/`AttendanceService`/`AttendanceRepository`/
  `AuditLogRepository` methods verified against each method's actual
  parameter list (extracted via `ast`, not by inspection alone).
- Migration/model-registration sanity check — `alembic/versions/`
  still contains exactly the same four revision files as Stage 2 ended
  with; `e1208296dad5` (Stage 1's attendance/audit-log migration) is
  byte-for-byte untouched.
- Line-length scan (100-char, matching the project's Ruff config) — 0
  lines over, after wrapping violations found in `csv_export.py`,
  `attendance_http_helpers.py`, and `test_attendance_http.py` during
  authoring.
- Trailing-whitespace scan — 0 matches across all Stage 3 files.
- Broad-exception scan — **1 match**, in `read_service.py`'s
  `_authorize_teacher_scope`: the same deliberate, documented
  `except Exception` pattern as Stage 2's `BlockedAuditWriter` caller
  (a blocked-audit write failure must never replace the original
  concealed authorization error). Reported honestly, not as zero.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan — 0 matches.
- Secret/debug-print scan — 0 matches.

## Checks/tests not executed this session

`pytest` is **not installed** in this sandbox (confirmed directly:
`python3 -c "import pytest"` raises `ModuleNotFoundError`), and this
sandbox has no network egress to install it or any other dependency
(`asyncpg`, `httpx`, etc. are also unconfirmed as installed — not
re-checked individually since `pytest` itself is already absent).
Docker, Ruff, and mypy are unavailable for the same reason recorded in
every prior Phase 3/4 checkpoint. As a direct consequence:

- The four new Stage 3 HTTP test files were never collected or run by
  `pytest` in this session. They are syntactically valid
  (`compileall`-clean) and structurally consistent with the
  already-passing Stage 1/2 fixture conventions (`client_db`,
  `db_session`, `phase3_http_helpers`), but **not runtime-verified
  here**.
- No new endpoint in this checkpoint has been exercised against a real,
  migrated PostgreSQL database. Every claim above about behavior (e.g.
  "returns 404", "audit row is written") is a claim about what the code
  is written to do, verified by static/structural review — not a claim
  that a test run confirmed it.
- `ruff check`/`ruff format --check`/`mypy` have not been run against
  any Stage 3 file. The line-length/trailing-whitespace/broad-exception
  scans above are hand-rolled approximations of a subset of what Ruff
  would check, not a substitute for it.

No check above is claimed to have passed where it did not actually run.

## Warnings and limitations

- The `classroom_id`/`subject_id`-required design decision (see
  "Genuine design decisions" #1) is a real, documented product-shape
  choice, not a bug — but it does mean an admin cannot currently ask
  "show me all attendance across every classroom" in one call. If a
  future phase wants that, it is new scope, not something Stage 3
  silently blocked.
- `AttendanceReadService._authorize_teacher_scope` and
  `AttendanceService._authorize_teacher_scope` (Stage 2) are two
  separate, unlinked implementations of a structurally similar check.
  A future refactor could unify them behind one shared internal helper
  — deliberately not attempted in this stage, to avoid touching Stage
  2's already-reviewed file for an unrelated reason (see "Teacher
  read-scope authorization" above).
- No Git commit, branch, tag, or stash was created or modified in this
  session, per the Stage 3 brief's constraints.

## Explicitly out of scope this session

Phase 4 Stage 4 (final integration: authoritative Docker/pytest/Ruff/
mypy verification of everything Stage 1–3 built) and Phase 5 (face
recognition) are both untouched. No new migration was needed or
created — Stage 3 is pure application-layer work over Stage 1's
existing schema.

## Exact Stage 4 starting point

Phase 4 Stage 4 is final integration and authoritative verification —
not new application code. Starting point:

1. Run the Docker test gate (`docker compose --profile test build
   backend_v2_test && docker compose --profile test run --rm
   backend_v2_test`), which applies `alembic upgrade head` (all four
   revisions, through `e1208296dad5`) against a real, ephemeral
   `postgres_test` service and then runs the full `pytest` suite,
   including all four new Stage 3 HTTP files and the unmodified Stage
   1/2 files.
2. Run `ruff format --check .`, `ruff check .`, and `mypy app` and fix
   any genuine finding — none of these three have run against any Stage
   3 file yet.
3. Re-verify every Critical/High `docs/AUDIT.md` finding this phase was
   meant to close (C4 in particular — object-level attendance
   authorization) now has passing, not just written, test coverage.
4. Only after 1–3 pass: write the consolidated
   `docs/HANDOVER_PHASE_4.md` (not created yet, per this stage's
   explicit instruction) summarizing all of Phase 4 Stage 1–4 together,
   and update `docs/IMPLEMENTATION_PLAN.md`'s Phase 4 status if the plan
   itself needs a status note.
5. Phase 5 (face recognition, ADR 0005) remains untouched and does not
   start until Phase 4 is fully closed.
