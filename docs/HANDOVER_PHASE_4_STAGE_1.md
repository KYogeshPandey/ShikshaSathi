# Handover — Rebuild Phase 4, Stage 1 (Attendance + Audit-Log Foundation)

**Status: Stage 1 in progress, not complete.** This checkpoint delivers
the relational attendance schema and the immutable audit-log foundation
as ORM models + stable domain errors + Pydantic schemas + repositories +
one Alembic migration, with database-backed tests. **No service layer,
no authorization/ownership checks, no FastAPI routers, no CSV export, and
no blocked-audit-logging behavior exist yet** — see "Explicitly out of
scope" below. This mirrors exactly how `docs/HANDOVER_PHASE_3_STAGE_1.md`
scoped Phase 3's own first checkpoint.

## What this checkpoint actually is

Built directly on the verified Phase 3 baseline (`docs/HANDOVER_PHASE_3.md`
§16 — 213 tests, Ruff, mypy all passing with Docker/PostgreSQL). This
session's new work:

1. `app/modules/attendance/` (models, errors, schemas, repository) — built
   from scratch.
2. `app/db/models.py` and `alembic/env.py` updated to register
   `AttendanceRecord` and `AuditLog` alongside every Phase 2/3 model.
3. Exactly one new Alembic migration, `e1208296dad5`, parented on Phase 3
   head (`32819e0a6027`).
4. `app/tests/conftest.py`'s per-test database cleanup extended to cover
   `attendance_records` and `audit_logs` (child-first, before the Phase
   2/3 tables they reference).
5. Five new test files covering model registration, migration round-trip,
   and both repositories.
6. ADR 0010 and this handover; `docs/PROGRESS.md` updated with a Phase 4
   Stage 1 section.

## Read first, in order

`docs/HANDOVER_PHASE_3.md` → this file → `docs/PROGRESS.md`'s "Phase 4
Stage 1" section (bottom of the file) → `docs/IMPLEMENTATION_PLAN.md`
Phase 4 → `docs/adr/0010-phase4-attendance-and-audit-trail.md` → the
module files themselves (`app/modules/attendance/`).

## Models delivered (all Stage 1, this checkpoint)

| Table | Module | Notes |
|---|---|---|
| `attendance_records` | `attendance` | one row per (student, classroom, subject, date); `status` enum (`present`/`absent`); `marked_by_user_id` FK to `users` (`RESTRICT`) |
| `audit_logs` | `attendance` | append-only; `outcome` enum (`success`/`blocked`); `actor_user_id` FK to `users` (`RESTRICT`, non-nullable); optional `classroom_id`/`subject_id` (`SET NULL`); sanitized JSONB `event_metadata` |

Full column-by-column rationale is in
`app/modules/attendance/models.py`'s module docstring and ADR 0010 — not
repeated here to avoid the two documents drifting out of sync.

## Key design decisions (see ADR 0010 for full rationale)

- **UUID primary keys everywhere**, continuing the Phase 2/3 convention.
- **No attendance-session table** — the (classroom, subject, date) triple
  already captured by `attendance_records` is the simplest schema that
  satisfies the documented Phase 4 acceptance criteria.
- **Audit logs are structurally append-only**: no `updated_at` column, and
  `AuditLogRepository` exposes only `create`/`get_by_id`/`list`/`count` —
  verified by a dedicated regression test, not just by omission.
- **Maximum bulk-attendance batch size is 200 records**
  (`app.modules.attendance.schemas.MAX_BULK_ATTENDANCE_ROWS`), enforced by
  the Pydantic schema itself (`Field(min_length=1, max_length=200)`),
  along with a model-level validator rejecting duplicate
  `student_profile_id` values within one request.
- **`aggregate_counts` is a single-query aggregation** — `(total, present,
  absent)` via one `SELECT` using `FILTER (WHERE ...)` aggregates, not
  three round trips or an in-Python scan over every row.

## Explicitly out of scope for this checkpoint

- No `AttendanceService` or `AuditLogService` — no transaction
  orchestration, upsert logic, or reference/ownership validation exists
  yet.
- No authorization/ownership-check errors are defined yet in
  `app.modules.attendance.errors` — only uniqueness (`AttendanceRecordAlreadyExistsError`),
  not-found (`AttendanceRecordNotFoundError`, `AuditLogNotFoundError`),
  and date-range (`AttendanceInvalidDateRangeError`) errors exist. Scope-
  denial errors (teacher ownership, student self-service) are Stage 2's
  responsibility.
- No FastAPI routers for attendance or audit logs — nothing in this
  module is reachable over HTTP yet. Every test in this stage calls the
  repositories directly (mirroring `app.tests.test_academics_repository`'s
  established pattern), not through `client_db`.
- No CSV export.
- No blocked-audit-logging behavior — that requires the Stage 2
  authorization layer to exist first.
- Phase 4 Stage 2 (service layer, authorization, routers, stats, CSV
  export) and everything after it is untouched.
- **Do not treat this checkpoint as "Phase 4 complete."** It is Stage 1
  only, exactly as `docs/HANDOVER_PHASE_3_STAGE_1.md` was for Phase 3.

## Migration

- **Revision:** `e1208296dad5` — `create_attendance_and_audit_logs`
- **Parent (`down_revision`):** `32819e0a6027` (Phase 3 head — immutable,
  not edited)
- Creates the `attendance_status` and `audit_outcome` native enums, then
  `attendance_records` and `audit_logs`, in FK-dependency order.
- `downgrade()` reverses this exactly (`audit_logs` then
  `attendance_records`, then both enums dropped last), landing back at
  Phase 3 head with every Phase 1-3 table and enum untouched.
- Constraint/index names are written out explicitly in the migration to
  match the naming convention in `app/db/naming.py` and each model's
  `__table_args__` — verified this session by an AST-based name diff
  between `app/modules/attendance/models.py` and the migration file (see
  "Checks actually performed" below); every FK/PK name not written
  explicitly in the ORM model is generated by the shared naming
  convention and matches the migration's explicit name exactly.
- **Not runtime-verified** in this sandbox (no Docker, no reachable
  PostgreSQL, no installed `sqlalchemy`/`alembic`/`fastapi`/`pytest` —
  confirmed empirically, consistent with every prior Phase 3 checkpoint
  in this same sandbox). Verified only by manual, column-by-column
  comparison against `AttendanceRecord`/`AuditLog`'s `__table_args__`,
  plus the automated scans below.

**The repository owner should run the full Docker gate before trusting
this checkpoint's runtime behavior:**

```bash
docker compose --profile test build backend_v2_test
docker compose --profile test run --rm backend_v2_test
```

Expected: every new Stage 1 test passes (repository behavior, model
registration, migration round-trip upgrade -> downgrade to
`32819e0a6027` -> re-upgrade), Ruff format/lint pass, and mypy passes.
Any failure should be fixed before Stage 2 begins.

## Checks actually performed this session

- `python -m compileall -q app alembic scripts` — **passed**, zero syntax
  errors across the whole tree (including every new/modified file).
- Custom AST-based internal `app.*` import-resolution scan — **353/354
  resolved**; the one flagged case (`app/main.py`'s
  `from app.api.routes import health`) is a known false-positive class
  already documented in Phase 3's own closure session (importing a
  submodule of a package, not a name defined in that package's
  `__init__.py`) and predates this session's changes.
- Model-registration / migration-table-name diff: every `__tablename__`
  across all `app/modules/**/models.py` files (12 total, including this
  session's two new ones) diffed against every `op.create_table`/
  `op.drop_table` name across **all three** migration files — **12/12
  match exactly** in both directions, with every table created in
  exactly one migration and dropped in exactly one migration's
  downgrade.
- Constraint/index name diff between `app/modules/attendance/models.py`
  and the new migration file — every name either matches literally or is
  generated by `app/db/naming.py`'s shared naming convention and
  confirmed to match the migration's explicit name (all four new FK
  names and both new PK names).
- Trailing-whitespace scan across the new/modified files — **0
  matches**.
- Line-length scan against the configured Ruff `line-length = 100` —
  **0 lines over 100 characters** (one file needed a wrap after initial
  authoring; fixed and re-verified in this session).
- Broad-exception scan (`except Exception`/bare `except:`) — **0 matches**
  in `app/modules/attendance/`.
- TODO/FIXME/`NotImplementedError`/fake-assertion (`assert True`) scan —
  **0 matches**.
- Secret/debug-print scan — **0 matches** in the new module.

## Checks unavailable in this sandbox

- `pip install <anything>` — confirmed blocked (no network egress),
  consistent with every prior Phase 3 session in this same sandbox.
  `fastapi`, `pydantic`, `sqlalchemy`, `asyncpg`, `alembic`, `pytest`,
  `pytest-asyncio`, `httpx`, `structlog` are all unavailable, so no
  application import, no `pytest` collection/run, and no `alembic` CLI
  invocation was possible.
- `ruff format --check .` / `ruff check .` — unavailable, `ruff` not
  installed.
- `mypy app` — unavailable, `mypy` not installed.
- `docker compose ...` — unavailable, Docker itself is not present.

No check above is claimed to have passed. Where full execution wasn't
possible, the closest available static/structural verification was
performed instead and is never conflated with the runtime check it
stands in for.

## Must NOT be redone

- Do not regenerate or restart any Phase 1-3 module.
- Do not edit migration `32819e0a6027` (Phase 3 head) or any earlier
  migration.
- Do not re-run the Phase 0 audit or Phase 1/2/3 scaffolding.

## Recommended next task (Stage 2, not started here)

Per `docs/IMPLEMENTATION_PLAN.md` Phase 4 and this session's own brief,
Stage 2 is: `AttendanceService` (transaction-owned bulk-mark with
teacher-ownership authorization and upsert behavior),
authorization/scope-denial errors, the blocked-audit-logging design
described in ADR 0010's "Consequences" section, FastAPI routers
(bulk-mark, detail, stats, daily, export, student self-service,
admin-only audit-log reads), and CSV export — see
`docs/IMPLEMENTATION_PLAN.md` Phase 4's full acceptance criteria, which
still apply in full and are not modified by this Stage 1 checkpoint.
