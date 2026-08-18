# Handover - Rebuild Phase 4 (Attendance Core and Audit Trail) - Closure

**Status: COMPLETE and authoritatively verified on 2026-08-01.**

This document consolidates Phase 4 Stages 1-4. The stage-specific handovers
remain the detailed authoritative record for their own checkpoints:

- `docs/HANDOVER_PHASE_4_STAGE_1.md`
- `docs/HANDOVER_PHASE_4_STAGE_2.md`
- `docs/HANDOVER_PHASE_4_STAGE_3.md`

No Phase 5 face-recognition implementation was started.

## 1. Phase 4 objective

Deliver a relational, transactional, authorized, and audited attendance
workflow on top of Phase 3's classrooms, subjects, student profiles, teacher
profiles, and teacher assignments.

The completed surface includes:

- transactional bulk attendance marking;
- attendance detail and daily reads;
- overall, student, and classroom statistics;
- student self-service attendance reads;
- CSV export with spreadsheet-formula-injection protection;
- successful-write audit records;
- independently persisted blocked-access audit records;
- admin-only audit-log read APIs;
- object-level teacher assignment enforcement.

## 2. Stage 1 - models, migration, and repositories

Stage 1 introduced:

- `AttendanceRecord`;
- `AuditLog`;
- `AttendanceStatus`;
- `AuditOutcome`;
- attendance and audit-log repositories;
- ORM registration and test cleanup support;
- Alembic revision `e1208296dad5`.

The migration's parent is Phase 3 revision `32819e0a6027`.

The verified migration chain is:

`98161483914f -> 6eeb9420bf8b -> 32819e0a6027 -> e1208296dad5`

## 3. Stage 2 - transactional writes and audit behavior

Stage 2 delivered `AttendanceService.bulk_save` with service-owned transaction
boundaries.

Behavior verified during closure:

- an invalid later student produces zero partial attendance writes;
- a forced repository failure rolls back the complete batch;
- a failed success-audit insertion rolls back attendance writes;
- no success audit survives a failed attendance transaction;
- successful writes remain attributable to the acting user;
- inactive teacher profiles and inactive/missing assignments are rejected;
- unrelated teacher access is concealed rather than disclosing resource scope;
- blocked attempts produce exactly one blocked audit record.

Blocked audit persistence deliberately uses an independent session/transaction
so the rejected request's rollback does not erase the security event.

## 4. Stage 3 - reads, statistics, CSV, and audit-log APIs

Stage 3 delivered:

- `POST /api/v1/attendance/bulk`;
- `GET /api/v1/attendance/detail`;
- `GET /api/v1/attendance/daily`;
- `GET /api/v1/attendance/stats`;
- `GET /api/v1/attendance/export`;
- `GET /api/v1/attendance/me/detail`;
- `GET /api/v1/attendance/me/stats`;
- `GET /api/v1/audit-logs`;
- `GET /api/v1/audit-logs/{id}`.

Authorization rules:

- admins use the documented override;
- teachers require an active teacher profile and active assignment for the
  requested classroom/subject scope;
- unrelated teacher access is returned as concealed `404`;
- students cannot supply another student's profile ID on self-service routes;
  their profile is derived from the authenticated user;
- audit-log reads are admin-only and read-only.

CSV behavior:

- generated fully in memory;
- stable server-controlled columns and filename;
- UTF-8 output;
- no temporary file;
- cells beginning with `=`, `+`, `-`, or `@` are escaped to prevent spreadsheet
  formula injection.

## 5. Stage 4 - final integration fixes

Authoritative runtime verification initially exposed two genuine failure
classes.

### 5.1 Event-loop-safe blocked audit writer

The original writer obtained a globally cached SQLAlchemy engine. Under
function-scoped async pytest loops, that engine could retain connections tied
to a closed event loop.

The final design:

- constructs an independent `async_sessionmaker` from the caller
  `AsyncSession`'s active `AsyncEngine`;
- keeps blocked audit persistence independent of the rejected transaction;
- remains injectable for tests;
- does not allow an audit-write failure to replace the original concealed
  authorization error.

Affected application files:

- `backend_v2/app/modules/attendance/service.py`
- `backend_v2/app/modules/attendance/read_service.py`

### 5.2 Rollback-safe tests

Several tests read ORM attributes after service rollback had expired the
instances, causing an attempted asynchronous lazy load outside a greenlet.

The tests now capture primitive UUID values before the rollback boundary and
use those scalar values in later assertions.

### 5.3 Earlier migration test compatibility

The Phase 3 round-trip test previously assumed Phase 3 revision
`32819e0a6027` would remain the repository-wide `head`.

It now:

1. upgrades to current head;
2. moves explicitly to the Phase 3 revision under test;
3. exercises the Phase 3 downgrade/re-upgrade round trip;
4. restores the database to the latest Phase 4 head.

No migration file was changed to achieve this.

### 5.4 Quality-gate fixes

Closure also applied:

- Ruff formatting;
- import organization;
- removal of unused `noqa` directives;
- explicit generic type arguments;
- typed SQLAlchemy `UniqueConstraint` narrowing;
- precise test-hook keyword argument typing.

These were mechanical quality-gate fixes and did not change the Phase 4 API
contract.

## 6. Authoritative verification

All commands used the Docker PostgreSQL test service.

### Phase 4 targeted suite

**98 passed, 0 failed.**

Coverage included:

- model registration;
- Phase 4 migration behavior;
- attendance repository;
- audit-log repository;
- transactional attendance service;
- attendance HTTP routes;
- statistics;
- CSV export;
- audit-log HTTP routes.

### Complete backend suite

**311 passed, 0 failed, 10 warnings.**

The warnings are dependency deprecations from Starlette/httpx and httpx's
per-request cookie API. They are non-blocking but should be removed during
dependency-maintenance work.

### Formatting, lint, and typing

- Ruff format: **133 files already formatted**.
- Ruff lint: **All checks passed**.
- mypy: **Success: no issues found in 126 source files**.

### Migration state

- `alembic upgrade head`: passed.
- `alembic heads`: `e1208296dad5 (head)`.
- `alembic current`: `e1208296dad5 (head)`.

## 7. AUDIT C4 closure status

AUDIT C4 is closed for attendance functionality in `backend_v2`.

Passing tests now demonstrate that:

- teachers cannot read or write unrelated attendance scopes;
- active teacher assignment is checked in the service layer;
- admins retain the intended override;
- blocked attempts are concealed and independently audited;
- both successful and blocked audit entries are visible through authorized
  audit-log reads.

The original Flask/Mongo backend remains unchanged and retains its historical
C4 finding until retirement. This closure applies only to the rebuilt FastAPI
backend.

## 8. Build qualification

A fresh `backend_v2_test` image was built successfully before the runtime
verification cycle.

A later rebuild retry failed while pip resolved Pydantic because no matching
`pydantic-core` distribution could be obtained from the package source.
Dependency declarations had not changed.

All final gates used the previously successful test image with the current
local `backend_v2` directory bind-mounted to `/workspace`. Therefore tests,
Ruff, mypy, and Alembic all ran against the exact current source tree.

Before deployment or CI release, retry a clean Docker build when package
registry/network resolution is healthy.

## 9. Repository state and safety

No Git commit, branch, tag, stash, reset, restore, or clean command was
performed.

Pre-existing legacy modifications and deletions were preserved. In
particular, Phase 4 closure did not attempt to repair, discard, or stage the
legacy Flask/React working-tree changes.

Real `.env` files, secrets, `.git`, caches, virtual environments,
`node_modules`, and generated test artifacts must remain excluded from any
shared closure archive.

## 10. Phase 4 completion verdict

Phase 4 is complete.

Its implementation, migration state, PostgreSQL behavior, test suite,
formatting, linting, and type checking are all verified.

There is no Phase 4 Stage 5. The next numbered work item is the separate
Phase 5 face enrollment and recognition workflow.

## 11. Exact next step

1. Create and verify a clean Phase 4 closure archive.
2. Preserve the current working tree; do not commit yet.
3. Resolve ADR 0005 before implementing a face-recognition provider.
4. Start Phase 5 only after the closure archive has been verified.
