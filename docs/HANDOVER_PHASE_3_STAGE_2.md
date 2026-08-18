# Handover — Rebuild Phase 3 Stage 2

## Status

**Stage 2 implementation is complete; runtime verification is not.** Do not
mark Phase 3 complete or Docker-verified. Stage 1 migration
`32819e0a6027` and all PostgreSQL-backed Stage 1/2 tests still need the
explicit Docker/PostgreSQL gate. Phase 3 final integration is pending and was
not started.

## What Stage 2 adds

- Focused async services for classrooms, subjects, teacher profiles, student
  profiles, teacher assignments, student classroom membership, timetable,
  and announcements.
- A shared service transaction boundary that commits only after a complete
  operation and rolls back unfinished transactions without broadly catching
  `Exception`.
- Separate versioned routers under `/api/v1`; no giant academic router.
- Admin create/read/list/update/deactivate APIs for every Stage 1 aggregate
  plus assignment and classroom-membership operations.
- Database-derived teacher/student scope for profiles, classrooms, subjects,
  timetable entries, and announcements.
- `404` concealment for private/unrelated objects after the caller passes the
  role gate; role denial remains `403`.
- Timetable creation/update requires a matching active teacher assignment.
- Global, teacher-role, student-role, and classroom announcement audiences.
- Offset pagination with `items`, `total`, `limit`, and `offset`.
- PostgreSQL HTTP tests using the existing `AsyncClient` +
  `ASGITransport` fixtures.

## Announcement audience extension

Stage 1 deliberately represented only `all` and `classroom`, but the Stage 2
acceptance criteria explicitly require role-audience visibility. Stage 2
therefore adds `teacher` and `student` to the existing enum; it does not add a
second audience mechanism. Because the Stage 1 migration has not yet passed
or been applied by its pending Docker gate, the still-unverified
schema-defining revision `32819e0a6027` was extended in place and remains the
migration head. See ADR 0008.

## Authorization behavior

- Authentication is unchanged and reused from Phase 2.
- Missing, malformed, deleted-user, or inactive-user authentication: `401`.
- Authenticated wrong role: `403`.
- Allowed role but another user's private/unrelated object: resource-specific
  `404`.
- Duplicate/state conflict: stable `409` domain error.
- Invalid request body/reference: `422` where applicable.
- Request-ID and the standard error envelope remain centralized.
- Announcement authors, current profile identity, role, assignments, and
  student classroom membership are always derived from authenticated/database
  state, never trusted from a client ownership claim.

## HTTP tests added

- `app/tests/test_phase3_admin_http.py`
  - unauthenticated/inactive/role-denied behavior
  - request-ID error propagation
  - classroom/subject CRUD, pagination, duplicates, deactivation
  - teacher/student profile creation and profile conflicts
  - membership assignment and missing classroom
  - teacher assignment creation, missing references, duplicates, deactivation
- `app/tests/test_phase3_scoped_access_http.py`
  - teacher own profile and assigned classroom/subject/timetable
  - teacher denial for another profile and unrelated resources
  - student own profile/classroom/relevant subject/timetable
  - student denial for another profile and unrelated resources
- `app/tests/test_phase3_announcements_timetable_http.py`
  - timetable assignment requirement, collision `409`, validation, update,
    deactivation
  - global, role, and classroom announcement visibility
  - unrelated audience denial, inactive exclusion, admin inactive listing
- `app/tests/test_service_transaction.py`
  - commit after success
  - rollback on operation failure
  - rollback when commit itself fails

All tests use the existing real-PostgreSQL fixtures. No fake database or
mocked authorization layer was added.

## Verification in this environment

- Docker was not run, per the Stage 2 task restriction.
- Windows `python`, `python3`, Ruff, mypy, and pytest executables were not
  available.
- `py -3.12` was attempted and reported `No installed Python found`.
- A WSL Python check was attempted but the sandbox denied WSL instance access.
- Repository-wide line-length inspection against Ruff's 100-character limit
  passed after fixing the two lines it initially reported.
- Full changed-file review and placeholder/broad-catch scans are recorded in
  `docs/PROGRESS.md`.

No unavailable check is claimed as passed.

## Required next gate

Do not run it as part of this checkpoint. On a Docker-enabled machine:

```bash
docker compose --profile test build backend_v2_test
docker compose --profile test run --rm backend_v2_test
```

The gate must apply `32819e0a6027`, run all existing and new tests, then run
Ruff format/lint and mypy. Fix every failure before Phase 3 finalization.

## Pending

- Docker/PostgreSQL Stage 1 migration round trip.
- Execution of all Stage 1 repository tests and Stage 2 HTTP tests.
- Ruff format/lint and mypy in an environment where those tools exist.
- Phase 3 final integration work, including the separately planned bulk
  import scope.
- Phase 4 and later work.

## Blockers

Runtime verification is blocked only by the current task/environment
restriction: Docker must not be run, and no local Python toolchain is
installed. Implementation itself has no known blocker.
