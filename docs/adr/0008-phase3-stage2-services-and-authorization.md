# ADR 0008: Phase 3 Stage 2 services and object authorization

## Status

Accepted.

## Context

Phase 3 Stage 2 adds service-layer transactions, management APIs, and
teacher/student read access on top of the Stage 1 models and repositories.
The Stage 2 acceptance criteria also require role-scoped announcement
visibility, while Stage 1 represented only global and classroom audiences.

## Decisions

1. Resource routers remain separate (`classrooms`, `subjects`, teacher and
   student profiles, assignments, timetable, announcements) and mount under
   `/api/v1`. They do not query ORM models directly.
2. Services own write transaction boundaries. The shared
   `service_transaction` helper commits only after the entire operation
   succeeds and rolls back unfinished transactions in `finally`, without a
   broad exception catch.
3. Role denial remains `403` through Phase 2's `require_roles`. A caller with
   an allowed role requesting another user's private or unrelated object
   receives the resource's normal `404`, concealing object existence.
4. Teacher and student scope is always derived from the authenticated
   database user, role-linked profile, active assignments, and classroom
   membership. Client-supplied ownership identifiers are never authoritative.
5. Timetable writes require an active teacher assignment matching the full
   teacher-profile, classroom, and subject triple.
6. Announcement audience extends the existing native enum with `teacher` and
   `student`. These values, like `all`, have no classroom-association rows.
   `classroom` remains the only value that requires association rows.
7. Because revision `32819e0a6027` has not passed or been applied by the
   pending Docker/PostgreSQL Stage 1 gate, the two enum values are added to
   that still-unverified schema-defining migration rather than creating a
   follow-up migration whose only purpose would be to amend an unapplied
   migration.

## Consequences

- Admins receive full management APIs; teachers and students receive only
  database-scoped reads.
- Global, role, and classroom announcements share one normalized audience
  mechanism.
- Migration head remains `32819e0a6027`; its PostgreSQL round-trip is still
  pending and must be verified before Phase 4 begins.
