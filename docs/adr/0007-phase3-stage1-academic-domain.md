# ADR 0007: Academic domain, profiles, and announcements foundations (Phase 3 Stage 1)

## Status
Accepted (Stage 1 scope only — model/repository layer; Stage 2's
service/router layer may extend but should not silently redesign these
decisions). Announcement audience Decision 6 is extended by ADR 0008
with the Stage 2-required `teacher` and `student` enum values.

## Context
Phase 3 Stage 1 needed to add the academic domain (`Classroom`,
`Subject`, `TeacherAssignment`, `TimetableEntry`), role-linked profile
data (`TeacherProfile`, `StudentProfile`), and announcements
(`Announcement`, `AnnouncementClassroom`) described at a spec level in
`docs/ARCHITECTURE.md` §2 and scoped in `docs/IMPLEMENTATION_PLAN.md`
Phase 3, plus the Stage 1 brief's own explicit instructions (avoid
comma-separated ID lists in favor of explicit association
tables/models; enforce "one profile per user" and role/profile
matching; define an explicit audience/visibility representation for
announcements). Several concrete decisions were not already settled by
earlier documentation and had to be made now. This ADR records them so
they are not silently redesigned in Stage 2.

## Decisions

### 1. UUID primary keys, continuing ADR 0006
No project document says otherwise for Phase 3, so the existing
enumeration-resistance rationale from ADR 0006 is simply continued,
not re-litigated, for every Stage 1 table.

### 2. Soft delete (`is_active`) for standalone entities, not for pure associations
`Classroom`, `Subject`, `TeacherProfile`, `StudentProfile`, and
`TeacherAssignment` all carry `is_active`, matching the legacy app's own
soft-delete convention (`docs/AUDIT.md`/`docs/LEGACY_MIGRATION_MAP.md`)
and keeping historical assignments/timetable entries referencing a
real, inspectable row instead of an orphan. `AnnouncementClassroom`
deliberately does **not** — a row's existence *is* its state (a
classroom is or isn't in an announcement's audience); there is no
independent lifecycle to soft-delete.

### 3. Explicit association tables/models for every genuine many-to-many
`TeacherAssignment` (teacher_profile × classroom × subject) and
`AnnouncementClassroom` (announcement × classroom) are both real,
first-class tables with their own primary key, not a comma-separated ID
column bolted onto one side of the relationship — directly required by
the Stage 1 brief. `StudentProfile.classroom_id` is the one deliberate
exception: it is a plain nullable foreign key, not an association
table, because student→classroom is many-to-one (one classroom, many
students; each student in at most one classroom at a time), matching
the legacy app's own single-`classroom_id` model — an association table
is required only where the relationship is genuinely many-to-many,
which this is not.

### 4. Role-match and audience-consistency invariants live in the repository layer, not a DB CHECK constraint
Both `ProfileRepository.create()`'s "the linked user's role must match
the profile type" and `AnnouncementRepository.create()`'s "audience
'all' has no classroom rows, audience 'classroom' has at least one" are
invariants that depend on a **different table's** row (`users.role` in
the first case; the presence/absence of `announcement_classrooms` rows
in the second). PostgreSQL cannot express either as a single-table
CHECK constraint without a trigger. No project document mandates a
trigger-based approach, so the simplest safe MVP rule is chosen
instead: the repository loads/checks the referenced state and raises a
named domain error before ever inserting a row. This is a documented,
known structural limitation (a row inserted by raw SQL bypassing the
repository would not be caught), not assumed airtight.

### 5. Timetable collision rule: exact-start-time only, not general interval overlap
No project document defines an exact overlap-detection invariant for
timetable slots. The simplest safe MVP rule is chosen: an exact
same-classroom-same-day-same-start-time collision, or an exact
same-teacher-same-day-same-start-time collision, is rejected via two
database-level unique constraints (`uq_timetable_entries_classroom_day_start`,
`uq_timetable_entries_teacher_day_start`). Detecting partially
*overlapping* but differently-timed slots (e.g. 09:00–10:00 vs.
09:30–10:30) is **not** enforced in Stage 1 — flagged as a known
limitation for Stage 2's service layer to potentially extend with an
explicit overlap query (e.g. a `tstzrange`/exclusion-constraint
approach), if a future project document requires it.

### 6. Announcement audience: a native enum plus an explicit association, not a denormalized flag
`Announcement.audience` is a native PostgreSQL enum
(`announcement_audience`: `all` / `classroom` / `teacher` / `student`),
the same enumeration-safety pattern as `UserRole`/`DayOfWeek` — an
invalid audience value is structurally impossible to store. Stage 1
initially defined only `all` and `classroom`; ADR 0008 added the two
role values before the migration's first runtime gate. The specific
classroom targets for a `classroom`-scoped announcement live in the
explicit `announcement_classrooms` table (Decision 3), not a JSON/array
column. All other audience values have no association rows.

### 7. `Announcement.author_user_id` uses `ondelete="RESTRICT"`, not `CASCADE`
Every Phase 3 profile FK to `users.id` uses `CASCADE`, because the
child row (a profile) is meaningless without its user. An announcement
is different: it is standalone content with its own audit-trail value
(`docs/ARCHITECTURE.md` §8), and this app's user-removal path is a soft
`is_active` flip, not a hard delete (`docs/AUDIT.md`'s audit-log
discussion). `RESTRICT` means a genuine hard delete of a user who has
posted announcements fails loudly instead of silently destroying
announcement history — consistent with this rebuild's fail-loud-not-
silent philosophy (`docs/ARCHITECTURE.md` §6).

## Alternatives considered
- **Comma-separated/JSON-array classroom-target lists on `Announcement`**
  (matching the legacy Mongo document shape). Rejected: no referential
  integrity, no index support, and directly contrary to the Stage 1
  brief's explicit instruction to use explicit association
  tables/models for many-to-many relationships.
- **Free-form values such as `"role:teacher"` / `"role:student"`.**
  Rejected in favor of the finite `teacher` and `student` enum values
  added by ADR 0008. Stage 1 initially deferred role audiences, but
  Stage 2's explicit visibility requirements resolved that decision
  before migration `32819e0a6027` was runtime-applied.
- **Trigger-enforced role-match/audience-consistency at the database
  level.** Rejected for Stage 1 as more infrastructure than any project
  document requires; the repository-layer check is documented as a
  known, narrower-than-airtight limitation instead.

## Consequences
- `classrooms`, `subjects`, `teacher_profiles`, `student_profiles`,
  `teacher_assignments`, `timetable_entries`, `announcements`, and
  `announcement_classrooms` are the eight tables added by migration
  `32819e0a6027` (parent: Phase 2 head `6eeb9420bf8b`).
- Stage 2's service layer and routers build directly on
  `ClassroomRepository`, `SubjectRepository`, `TeacherAssignmentRepository`,
  `TimetableRepository`, `TeacherProfileRepository`,
  `StudentProfileRepository`, and `AnnouncementRepository` without
  redesigning the invariants above.
- A future overlap-aware timetable rule (Decision 5) remains explicitly
  open for a later phase. Role-scoped announcement audiences are resolved
  by ADR 0008 and are part of migration `32819e0a6027`.
