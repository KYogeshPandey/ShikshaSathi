# Handover — Rebuild Phase 3 (Academic Domain, Profiles, Announcements, Bulk Import) — Closure

**Status: Phase 3 implementation complete; authoritative Docker/PostgreSQL
verification pending.** Everything in this document is either grounded in
direct source inspection performed in this closure session, in the AST/
compile-level static checks recorded under "Checks executed," or carried
forward unchanged from `docs/HANDOVER_PHASE_3_STAGE_1.md` and
`docs/HANDOVER_PHASE_3_STAGE_2.md`, which remain the authoritative record
for their own stages and are not rewritten here.
## 1. Phase 3 objective

Rebuild the legacy academic-domain and communications surface — classrooms,
subjects, teacher/student profiles, teacher-classroom-subject assignments,
timetable, and announcements — as real relational PostgreSQL tables with
full CRUD, on top of Phase 2's identity/auth/RBAC foundation, per
`docs/IMPLEMENTATION_PLAN.md`'s Phase 3 scope. This also folds in the
bounded CSV/XLSX bulk-import capability (ADR 0009) that the plan's Phase 3
"CSV/Excel import with validation and row limits" line item calls for.

## 2. Stage 1 — academic domain, profiles, announcements (models/repositories)

Delivered, reviewed, and handed over in full in
`docs/HANDOVER_PHASE_3_STAGE_1.md`. Summary only:

- ORM models + repositories + one Alembic migration for `classrooms`,
  `subjects`, `teacher_profiles`, `student_profiles`, `teacher_assignments`,
  `timetable_entries`, `announcements`, `announcement_classrooms`.
- `app/db/models.py` and `alembic/env.py` updated to register all eight
  new tables alongside Phase 2's `users`/`refresh_sessions`.
- `app/tests/conftest.py` cleanup extended to all eight tables in
  FK-safe (child-first) order.
- ADR 0007 records the academic-domain design decisions, including the
  deliberate **exact-start-time-only** timetable collision rule (not
  general interval-overlap detection — see ADR 0007 §5).
- No service layer, routers, or Phase 4 work existed at the end of Stage 1.

## 3. Stage 2 — services, routers, authorization

Delivered, reviewed, and handed over in full in
`docs/HANDOVER_PHASE_3_STAGE_2.md`. Summary only:

- Service-owned transaction boundaries (`app/db/transaction.py`'s
  `service_transaction`) for every write path.
- Seven modular routers: classrooms, subjects, teacher-profiles,
  student-profiles, teacher-assignments, timetable-entries, announcements.
- Admin CRUD for every entity; teacher/student object-level authorization
  via `app/modules/auth/authorization.py`'s `require_own_profile` /
  `require_related_resource` helpers, concealing unrelated records as a
  normal `404` rather than a `403` (role denial is the only thing that
  surfaces as `403`, at the `require_roles` dependency).
- Announcement audience model (`all` / `teacher` / `student` / `classroom`)
  and visibility rules.
- HTTP integration tests for admin, scoped-access, and announcement/
  timetable behavior. ADR 0008.

## 4. Final-integration and bulk-import fixes (this closure session + the
   interrupted session it continues)

### 4.1 Carried in from the interrupted session (verified, not redone)

- `backend_v2/app/modules/bulk_imports/` (parser, errors, schemas, service,
  router) — bounded CSV/XLSX import for `classrooms`, `subjects`,
  `teacher-profiles`, `student-profiles`.
- ADR 0009 (bounded bulk imports — scope, limits, and the deliberate
  "link to existing users only, never create accounts" boundary).
- Fixes described in the interrupted session's own summary: inactive-user
  handling, deterministic pagination, announcement query efficiency
  (batched classroom-id lookups avoiding N+1), explicit membership
  operations, stable employee-code conflict handling.

### 4.2 Found and fixed in this closure session

**Bug: XLSX numeric identifier cells failed validation.**
`app/modules/bulk_imports/parser.py`'s `_normalized_row()` passed
non-string XLSX cell values (`int`/`float`/`bool`) through to the Pydantic
`*Create` schemas unchanged. Pydantic v2's lax `str` validation does **not**
coerce `int`/`float` to `str`. Excel's default "General" number format
reads back a typed whole number (e.g. a classroom code, employee code, or
roll number entered as `12`) as a Python `int` or `float`, not `str` — so a
completely legitimate, common real-world XLSX cell would spuriously fail
row validation. Fixed by adding `_normalized_scalar()`:

- `bool` is left as a native bool (not stringified — stringifying `True`
  to `"True"` would turn a real boolean into an identifier-shaped string
  for no reason, even though it happens to still parse back).
- `int` becomes its plain decimal string (`12` -> `"12"`).
- `float` is rejected if `NaN`/infinite (`BulkImportFileError`, since
  neither is a legitimate identifier value); otherwise rendered as a clean
  decimal string with no spurious trailing zero (`12.0` -> `"12"`, `12.5`
  -> `"12.5"`).
- Anything else (e.g. a `datetime` cell) passes through unchanged, exactly
  as before — the fix is deliberately narrow and does not broadly coerce
  arbitrary Python objects.
- `data_only=True` (formula cells yield their last-cached value, never a
  formula string) and the empty-value/blank-string contract are unchanged.

Verified directly against the installed `openpyxl` (available in this
sandbox, unlike `fastapi`/`pytest`) that: whole-number floats round-trip
through a real workbook as `int` (`12.0` write -> `12` read, type `int`);
non-whole floats round-trip as `float`; `bool` round-trips as `bool`; and
— importantly — **`NaN`/infinity cannot round-trip through openpyxl's own
writer at all**: writing either produces an empty cell, read back as
`None`. This means the NaN/infinity rejection path can never be exercised
by a workbook built with openpyxl and is tested directly against the
normalization helper instead (see §12).

**Regression tests added:**
- `app/tests/test_bulk_import_parser.py` (new, DB-independent, always
  runs): direct unit tests of `_normalized_scalar`/`_normalized_row` for
  int, whole-float, decimal-float, bool, NaN, infinity, and pass-through
  of other object types.
- `app/tests/test_phase3_bulk_import_http.py` (extended): unauthenticated
  `401`, unsupported extension `422`, oversized file `413`, header row
  missing a required column, numeric-XLSX-identifier end-to-end import
  for `classrooms`/`subjects`/`teacher-profiles`/`student-profiles`, a
  failed row not blocking a later valid row in the same file, and an
  assertion that error responses never echo the submitted row or any
  password/token/hash-shaped field.

### 4.3 Reviewed, no genuine issue found

The remaining routers/services not yet explicitly reviewed in the prior
session (student-profile, timetable, subjects, assignments, announcements)
were checked in this session against: route prefix/method consistency,
response models, RBAC dependency correctness, object-scope enforcement,
`401`/`403`/`404`/`409` behavior, inactive-user/inactive-record handling,
absence of client-trusted ownership or role, and safe async access
patterns (no bare ORM-relationship lazy loads under `asyncpg`). All were
already consistent with the patterns verified elsewhere in Phase 3 —
in particular:

- `TimetableService` correctly conceals unrelated/stale-assignment entries
  as `404` for teacher/student, re-validates references and re-checks the
  DB collision constraints on both `create` and `update`.
- `AnnouncementRead` is built via `from_model`, combining the ORM row with
  a separately-queried `classroom_ids` list — there is no ORM
  `relationship()` to accidentally lazy-load under `asyncpg`.
- No duplicate `(method, path)` pair exists across any of the nine router
  files (see §12).

No code change was made to these files in this closure session.

## 5. Modules added (cumulative, Stage 1 + Stage 2 + bulk import)

- `app/modules/academics/` — models, repository, schemas, errors,
  `classrooms_service.py`/`_router.py`, `subjects_service.py`/`_router.py`,
  `assignments_service.py`/`_router.py`, `timetable_service.py`/`_router.py`,
  `normalization.py`.
- `app/modules/profiles/` — models, repository, schemas, errors,
  `teacher_service.py`/`_router.py`, `student_service.py`/`_router.py`,
  `membership_service.py`.
- `app/modules/announcements/` — models, repository, schemas, errors,
  `service.py`, `router.py`.
- `app/modules/bulk_imports/` — `parser.py`, `errors.py`, `schemas.py`,
  `service.py`, `router.py`.
- `app/db/transaction.py` — `service_transaction` (shared commit/rollback
  boundary helper).
- `app/modules/auth/authorization.py` — `require_own_profile`,
  `require_related_resource` (shared object-level authorization helpers).

## 6. Database tables and relationships

| Table | Module | Key relationships |
|---|---|---|
| `classrooms` | academics | referenced by `teacher_assignments`, `timetable_entries`, `student_profiles.classroom_id`, `announcement_classrooms` |
| `subjects` | academics | referenced by `teacher_assignments`, `timetable_entries` |
| `teacher_profiles` | profiles | 1:1 with `users` (unique `user_id`, `ON DELETE CASCADE`); referenced by `teacher_assignments`, `timetable_entries` |
| `student_profiles` | profiles | 1:1 with `users`; many-to-one to `classrooms` (nullable `classroom_id`, `ON DELETE SET NULL`) |
| `teacher_assignments` | academics | unique (teacher_profile, classroom, subject) triple; referenced by `timetable_entries` (indirectly, via the same triple) |
| `timetable_entries` | academics | (classroom, subject, teacher_profile, day_of_week, start_time); two collision-preventing unique constraints (classroom+day+start, teacher+day+start) — see ADR 0007 §5 for the exact-start-time-only scope |
| `announcements` | announcements | `audience` enum (`all`/`teacher`/`student`/`classroom`); no `author` FK stored as an ORM relationship (id only) |
| `announcement_classrooms` | announcements | association table, populated only when `audience = classroom` |

All soft-delete via `is_active`; no hard deletes anywhere in Phase 3.

## 7. Migration revision

`32819e0a6027` — `create_academics_profiles_announcements`
**Parent:** `6eeb9420bf8b` (Phase 2's `create_users_and_refresh_sessions`)

Verified locally with Docker and PostgreSQL:

- The migration chain upgraded successfully through:
  `98161483914f -> 6eeb9420bf8b -> 32819e0a6027`.
- All eight Phase 3 tables were created successfully against PostgreSQL.
- `app/tests/test_migrations_phase3.py` passed its upgrade, downgrade to
  `6eeb9420bf8b`, and re-upgrade round trip.
- ORM model registration and migration-table consistency checks passed.

Revision `32819e0a6027` has now passed the authoritative runtime gate and
must be treated as immutable. Any later schema change must use a new Alembic
revision.

## 8. Service and transaction architecture

Every write path opens `async with service_transaction(self._session):` —
commit on success, rollback on any exception, via `app/db/transaction.py`.
Repositories translate `IntegrityError` into stable domain errors (e.g.
`ClassroomCodeAlreadyExistsError`, `TimetableCollisionError`) after calling
`await self._session.rollback()` themselves, so a failed repository call
never leaves the session in an unusable "transaction rolled back" state for
whatever code runs next. Bulk imports run each row's `create()` call (and
therefore each row's own `service_transaction`) independently against one
shared `AsyncSession`, so successful rows commit independently of rows that
fail later or earlier in the same file — verified by direct code reading
(§4.2's `_validate_references`/`create` call chain) and by the new
`test_valid_rows_after_a_failed_row_still_import` regression test.

## 9. Routers and endpoint summary

Nine router files, 43 unique `(method, path)` route registrations, zero
duplicates (see §12). Full endpoint-by-endpoint inventory — method, path,
required role/scope, purpose, and `404`/`409` behavior — is in
`backend_v2/README.md`'s "Phase 3 endpoint inventory" and "Bulk CSV/XLSX
import" sections; not duplicated here to avoid the two documents drifting
out of sync.

## 10. RBAC and object-level authorization

- Role gate: `app/modules/auth/dependencies.py`'s `require_roles(...)` —
  `401` unauthenticated/inactive-user token, `403` wrong role.
- Object-level gate (teacher/student scoped reads): `require_own_profile`
  / `require_related_resource` — an unrelated but real object is concealed
  as the resource's normal `404`, never a `403` (a `403` would confirm the
  object exists; the `404` does not).
- No endpoint accepts a client-supplied role or ownership claim; every
  scope check is derived from the authenticated user's row plus a DB
  lookup (assignment/membership/authorship), never from a request body
  field.
- Bulk imports: `require_roles(UserRole.ADMIN)` only: no teacher/student
  bulk-import path exists at all.

## 11. Announcement audience rules

`all` / `teacher` / `student` / `classroom` — one Python `AnnouncementAudience`
enum (`app/modules/announcements/models.py`), one matching Postgres enum in
migration `32819e0a6027`, one matching Pydantic schema. Only `classroom`
accepts/requires `classroom_ids`; the other three reject them. Visibility
for list/read is evaluated per-role (admin sees everything; teacher sees
`all`/`teacher`/their assigned classrooms' `classroom` announcements;
student sees `all`/`student`/their own classroom's `classroom`
announcements) using a single batched classroom-id lookup per list call
(`list_classroom_ids_for_announcements`), not a per-row query.

## 12. Bulk CSV/XLSX import behavior

See `backend_v2/README.md`'s "Bulk CSV/XLSX import" section for the
full per-entity required/optional column tables, limits, and
partial-success semantics — summarized:

- Admin-only; `classrooms`, `subjects`, `teacher-profiles`,
  `student-profiles`.
- `.csv` (UTF-8, optional BOM) or `.xlsx` only; 2 MiB / 500-non-blank-row
  bounds enforced before row processing, via a hard-capped `file.read()`
  so an oversized upload is never buffered past the limit.
- No filesystem writes anywhere in the module — content is parsed
  entirely from the in-memory upload; nothing is persisted beyond what a
  successful row's own repository `create()` call writes to Postgres.
- Per-row independent commit/rollback (§8); response is `HTTP 200` with
  `success`, `imported_count`, `failed_count`, and a stable, safe `errors`
  list (no submitted-row echo, no password/token/hash field anywhere in
  the entities this module touches).
- XLSX read with `data_only=True` — no formula evaluation, no formula
  string leak.
- Route registered exactly once (`app/api/router.py`); confirmed by the
  duplicate-route AST scan in §14 finding zero collisions across all nine
  router files including `bulk_imports/router.py`.

## 13. Test inventory

Docker pytest collected and passed **213 test items** across the complete
`backend_v2/app/tests/` suite. Result: **213 passed, 0 failed, 10
non-blocking deprecation warnings**.

- `test_bulk_import_parser.py` — **new**, 9 tests, DB-independent.
- `test_phase3_bulk_import_http.py` — **extended** from 3 to 10 tests:
  added unauthenticated `401`, unsupported extension, oversized file,
  header missing a required column, numeric-XLSX-identifier import across
  all four entities, valid-row-after-failed-row, and no-secret-echo
  coverage. The three original tests (CSV row errors keeping valid rows,
  XLSX success + non-admin `403`, malformed file + row limit) are
  unchanged.

Coverage against the Phase 3 test-completeness checklist (model
registration, migration round-trip, repository behavior, service
transaction helper, admin management APIs, unauthenticated/inactive/
role-denied access, teacher/student own-profile and scoped access and
denial, all four announcement audiences, duplicate/code conflicts,
timetable collisions, pagination/filtering, error envelope + request-ID
propagation, bulk CSV/XLSX import including malformed files, missing
columns, per-row failures, row-limit, and unauthorized/role-denied
imports) is satisfied across the files listed above and in
`docs/HANDOVER_PHASE_3_STAGE_1.md` / `_STAGE_2.md`. No fake assertions or
mocked-implementation-only tests were added or found (see §14's scan).

## 14. Checks actually executed (this closure session)

All scoped to `backend_v2/` (and `docs/` for documentation review); legacy
`backend/`/`frontend/` untouched.

- `python -m compileall -q app alembic scripts` — **passed**, zero syntax
  errors.
- Custom AST-based internal `app.*` import-resolution scan (every
  `from app.* import name` across 106 files) — **106/106 files checked,
  0 unresolved imports.**
- Model-registration / migration-consistency scan: every `__tablename__`
  in `app/modules/**/models.py` diffed against every `op.create_table`
  name in `32819e0a6027` — **8/8 match exactly**, no missing/extra table.
- Duplicate route `(method, path)` scan across all nine `*router.py`
  files (including `bulk_imports/router.py`) — **43 unique routes, 0
  duplicates.**
- Trailing-whitespace scan across `app/alembic/scripts` — **0 matches.**
- Line-length scan against the configured Ruff `line-length = 100` —
  **0 lines over 100 characters.**
- Broad-exception scan (`except Exception`/bare `except:`) — only the
  three pre-existing Phase 1/2 occurrences (`app/db/session.py` x2,
  `app/core/middleware.py`, `app/tests/conftest.py`'s DB-unreachable
  `pytest.skip` path), all legitimate log-or-skip-and-reraise patterns;
  **zero in Phase 3 code.**
- TODO/FIXME/`NotImplementedError`/fake-assertion (`assert True`) scan —
  **0 matches** anywhere in `app/`.
- Secret/debug-print scan (`password|secret|api_key = "..."` pattern,
  plus a full-repo `find` for a real, non-`.example` `.env`) — **0
  matches**; only docstring mentions of `print()` as the anti-pattern
  being described, plus `scripts/bootstrap_admin.py`'s intentional
  non-secret status prints (email/id/role only, verified by direct read —
  pre-existing Phase 2 script, not modified).
- `pyproject.toml` parsed via `tomllib` — **valid**; `openpyxl` and
  `python-multipart` confirmed present in `project.dependencies` (not just
  `dev`), so the production image installs them too.
- `alembic.ini` parsed via `configparser` (interpolation disabled) —
  **valid**; confirmed no hardcoded `sqlalchemy.url`.
- `docker-compose.yml` parsed via `yaml.safe_load` — **valid**; confirmed
  exactly `postgres`, `backend_v2`, `postgres_test`, `backend_v2_test`
  services (no unscoped addition).
- Direct `openpyxl` (3.1.5, available in this sandbox) round-trip probing
  of the exact numeric/bool/NaN/infinity cases the parser fix depends on
  — see §4.2.

## 15. Checks unavailable in the closure sandbox — historical record

- `pip install fastapi` (or any package) — confirmed blocked: the
  sandbox's egress proxy returns `x-deny-reason: host_not_allowed` /
  "Could not find a version that satisfies the requirement" for PyPI.
  `fastapi`, `pydantic`, `sqlalchemy`, `httpx`, `pytest`,
  `pytest-asyncio`, `structlog`, `alembic` (the importable package, not
  the CLI concept) are all unavailable, so no application import, no
  `pytest` collection/run, and no `alembic` CLI invocation was possible.
  (`openpyxl` happens to already be present in this sandbox and was used
  for the direct round-trip verification in §4.2 — this is incidental,
  not evidence that the rest of the stack is installable.)
- `ruff format --check .` / `ruff check .` — unavailable, `ruff` not
  installed.
- `mypy app` — unavailable, `mypy` not installed.
- `docker compose ... ` (build/up/exec) — unavailable, Docker itself is
  not present in this sandbox.
- `curl http://localhost:8000/health/...` — unavailable, no running
  server.

No check above is claimed to have passed. Where full execution wasn't
possible, the closest available static/structural verification was
performed instead (§14) and is never conflated with the runtime check it
stands in for.

These limitations applied only to the closure sandbox. The previously
unavailable runtime and quality checks were subsequently executed
successfully on the repository owner's Docker-enabled machine; see §16.

## 16. Authoritative Docker/PostgreSQL verification completed

Local verification was completed on 2026-07-30 using the
`backend_v2_test` Docker Compose profile and PostgreSQL test service.

Results:

- Docker image `shikshasathi-backend_v2_test` built successfully.
- PostgreSQL test container started and passed its health check.
- Alembic upgraded successfully through revision `32819e0a6027`.
- Migration upgrade/downgrade/re-upgrade tests passed.
- Pytest collected 213 items: **213 passed, 0 failed**.
- **10 non-blocking deprecation warnings** remain.
- Ruff format: **113 files already formatted**.
- Ruff lint: **All checks passed**.
- Mypy: **Success: no issues found in 106 source files**.

Phase 3 has no remaining implementation, migration, test, formatting,
linting, or typing blocker.

## 17. Warnings and limitations

- - Phase 3 has now been runtime-verified with Docker and PostgreSQL. The
  authoritative gate passed with 213 tests, Ruff format, Ruff lint, and
  mypy across 106 source files.
- The 10 remaining warnings are dependency/test-client deprecation
  warnings and are non-blocking. They should be handled during a future
  dependency-maintenance pass rather than delaying Phase 4.
- The XLSX NaN/infinity rejection path (§4.2) is verified only at the
  unit level against the normalization helper directly — it is not (and,
  given openpyxl's own write behavior, cannot be) exercised through a real
  workbook built with openpyxl. A workbook authored by some other tool
  that *can* persist a literal NaN/Infinity numeric cell is the only
  scenario where this path would actually trigger in production; that
  remains untested at the file-parsing level.
- The timetable collision rule is intentionally exact-start-time-only, not
  general interval-overlap detection (ADR 0007 §5) — this is a documented
  Stage 1 MVP scope decision, not a defect, and is called out again here
  so it isn't mistaken for one during Phase 4 planning.
- Teacher/student profile bulk import links to an **existing** user by
  `user_id` only; it does not accept or normalize an email-based lookup,
  and does not create user accounts. This is ADR 0009's explicit scope
  boundary, not an oversight — flagged again here in case Phase 4 or a
  later usability pass wants to reconsider it.
- No Git commit was created at any point in Phase 3 (Stage 1, Stage 2, the
  interrupted session, or this closure session). The repository's git
  state is exactly as uncertain as `docs/HANDOVER_PHASE_1.md` /
  `docs/PROGRESS.md` left it after Phase 0/1 — this closure did not
  change that.

## 18. No Git commit performed

Confirmed: no `git commit`, `git add`, branch, tag, stash, or history
change of any kind was made in this closure session, consistent with
every prior Phase 3 session.

## 19. Exact Phase 4 starting point

Per `docs/IMPLEMENTATION_PLAN.md`, Phase 4 is **Attendance core and audit
trail** — attendance schema + transactional bulk-save, stats/detail/export
endpoints behind the same ownership-check pattern established in Phase 2/3,
and audit-log coverage extended to blocked/forbidden attempts.

All Phase 3 implementation and verification blockers have been cleared.
Phase 4 may now begin.

Before writing Phase 4 code:

1. Read this file, `docs/HANDOVER_PHASE_3_STAGE_1.md`,
   `docs/HANDOVER_PHASE_3_STAGE_2.md`, the final Phase 3 section of
   `docs/PROGRESS.md`, and the Phase 4 section of
   `docs/IMPLEMENTATION_PLAN.md`.
2. Build on revision `32819e0a6027`; do not edit the verified migration.
   Any schema change must use a new Alembic revision.
3. Do not redo Phase 3 models, services, routers, authorization, imports,
   or tests.
4. Treat legacy Phase 0 security decisions as separate maintenance items;
   they are not Phase 4 implementation blockers.
