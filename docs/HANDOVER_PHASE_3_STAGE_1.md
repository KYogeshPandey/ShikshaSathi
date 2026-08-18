# Handover — Rebuild Phase 3, Stage 1 (Academic Domain, Profiles, Announcements)

**Status: Stage 1 in progress, not complete.** This checkpoint delivers
the academic domain, role-linked profiles, and announcements as ORM
models + repositories + one Alembic migration, with database-backed
tests. **No service layer, no API routers, and no Phase 4 work exist
yet** — see "Explicitly out of scope" below.

## What this checkpoint actually is

This is a continuation of a Stage 1 checkpoint already in progress:
`app/modules/academics/` and `app/modules/profiles/` arrived already
implemented in the ZIP this session started from. They were inspected
against `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md` (Phase 2/3),
and the Stage 1 review checklist (UUID PKs, timestamps, FK `ondelete`
behavior, uniqueness constraints, indexes, no duplicated credential
fields, no comma-separated relationship IDs, repository transaction
ownership, safe domain-error mapping) — no genuine defect was found, so
neither module was rewritten or regenerated, per this checkpoint's
explicit instruction. This session's own new work is:

1. `app/modules/announcements/` (model, errors, schemas, repository) —
   built from scratch.
2. `app/db/models.py` and `alembic/env.py` updated to register every
   Phase 3 model alongside Phase 2's.
3. Exactly one new Alembic migration, `32819e0a6027`, parented on
   Phase 2 head (`6eeb9420bf8b`).
4. `app/tests/conftest.py`'s per-test database cleanup extended to
   cover all eight new tables in FK-safe order.
5. Five new test files covering all of the above.
6. This handover doc and the Phase 3 Stage 1 section appended to
   `docs/PROGRESS.md`.

## Read first, in order

`docs/HANDOVER_PHASE_2.md` (if resuming cold) → this file →
`docs/PROGRESS.md`'s "Phase 3 Stage 1" section (bottom of the file) →
`docs/IMPLEMENTATION_PLAN.md` Phase 3 → the five Stage 1 module files
themselves (`app/modules/academics/`, `app/modules/profiles/`,
`app/modules/announcements/`).

## Models delivered (all Stage 1, all reviewed this checkpoint)

| Table | Module | Notes |
|---|---|---|
| `classrooms` | `academics` | soft-delete via `is_active`; normalized+unique `code` |
| `subjects` | `academics` | soft-delete via `is_active`; normalized+unique `code` |
| `teacher_profiles` | `profiles` | 1:1 with `users` (unique `user_id`); role-match enforced in `TeacherProfileRepository.create` |
| `student_profiles` | `profiles` | 1:1 with `users`; nullable `classroom_id` (many-to-one, not an association table — see model docstring) |
| `teacher_assignments` | `academics` | explicit (teacher_profile × classroom × subject) association; unique triple |
| `timetable_entries` | `academics` | day_of_week enum + start/end time; two collision-preventing unique constraints (see "Timetable collision rule" below) |
| `announcements` | `announcements` | **new this checkpoint**; `AnnouncementAudience` enum (`all`/`classroom`); `author_user_id` FK uses `ondelete="RESTRICT"`, not `CASCADE` (see rationale in `app/modules/announcements/models.py`) |
| `announcement_classrooms` | `announcements` | **new this checkpoint**; explicit many-to-many association, only populated for `audience="classroom"` |

## Key design decisions carried into Stage 1 (not re-litigated here — see each model file's own docstring for full rationale)

- **UUID primary keys everywhere**, continuing the Phase 2 convention.
- **Soft delete (`is_active`)**, not row deletion, for every Stage 1
  entity except the pure association tables (`teacher_assignments`
  still has `is_active` for revocable assignments; `announcement_classrooms`
  does not — its row's existence *is* the state).
- **Explicit association tables/models for every genuine many-to-many**
  (`TeacherAssignment`, `AnnouncementClassroom`) — no comma-separated ID
  columns anywhere in Stage 1.
- **Role-match and audience-consistency invariants are enforced at the
  repository layer, not as single-table DB CHECK constraints**, because
  both depend on a *different* table's row (`profiles`' role match
  needs `users.role`; announcements' audience match needs the presence
  or absence of `announcement_classrooms` rows). This is documented as
  a known structural limitation (a row inserted via raw SQL bypassing
  the repository would not be caught), not silently assumed airtight.
- **Timetable collision rule (Stage 1 MVP only):** an exact
  same-classroom-same-day-same-start-time collision, or an exact
  same-teacher-same-day-same-start-time collision, is rejected via two
  unique constraints. Partially *overlapping* but differently-timed
  slots (e.g. 09:00–10:00 vs. 09:30–10:30) are **not** detected in
  Stage 1 — flagged as a known limitation for Stage 2's service layer.

## Explicitly out of scope for this checkpoint (per this checkpoint's own brief)

- No service-layer classes for academics/profiles/announcements.
- No FastAPI routers for any Stage 1 domain — Stage 1 is
  model/repository only, exactly as instructed.
- Phase 3 Stage 2 has not been started.
- Phase 4 (attendance) and everything after it is untouched.
- **Do not treat this checkpoint as "Phase 3 complete."** It is Stage 1
  only.

## Migration

- **Revision:** `32819e0a6027` — `create_academics_profiles_announcements`
- **Parent (`down_revision`):** `6eeb9420bf8b` (Phase 2 head)
- Creates all eight tables above plus the `day_of_week` and
  `announcement_audience` native enums, in FK-dependency order.
- `downgrade()` reverses this exactly (children before parents, enums
  dropped last), landing back at Phase 2 head.
- **Not runtime-verified** in this sandbox (no Docker, no reachable
  PostgreSQL, no installed `alembic`) — see `docs/PROGRESS.md`'s
  "Not verified this checkpoint" for the exact list. Verified only by
  manual, column-by-column comparison against every Stage 1 model's
  `__table_args__`.

## Verification actually performed vs. not performed

See `docs/PROGRESS.md`'s Phase 3 Stage 1 section, "Verification
actually performed this checkpoint" / "Not verified this checkpoint",
for the exact, honest list. In short: `python3 -m compileall` passed
across the whole tree, a custom AST cross-import checker found 277/277
internal imports resolving correctly, and manual review was performed
throughout — but `pytest`, `alembic`, `ruff`, `mypy`, and Docker could
not be run in this sandbox (no network egress, no Docker, no installed
dependencies — confirmed empirically). **The repository owner should
run the full Docker gate before trusting this checkpoint's runtime
behavior:**

```bash
docker compose --profile test build backend_v2_test
docker compose --profile test run --rm backend_v2_test
```

Expected: every new Stage 1 test passes, the Phase 3 migration
round-trip test passes, Ruff format/lint pass, and mypy passes. Any
failure should be fixed before Stage 2 begins.

## Must NOT be redone

- Do not regenerate or restart `app/modules/academics/` or
  `app/modules/profiles/` — they were reviewed, not defective, and
  preserved as-is.
- Do not re-run the Phase 0 audit or the Phase 1/2 scaffolding.

## Recommended next task (Stage 2, not started here)

Service-layer orchestration for academics/profiles/announcements
(ownership checks, cross-entity validation beyond what the repository
layer already does), followed by the first real Stage 2 FastAPI
routers — see `docs/IMPLEMENTATION_PLAN.md` Phase 3's original scope
text for the full acceptance criteria that still apply.
