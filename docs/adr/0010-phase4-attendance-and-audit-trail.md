# ADR 0010: Attendance core and audit-trail foundation (Phase 4 Stage 1)

## Status

Accepted for Stage 1 (models, schemas, errors, repositories, migration).
Service-layer transaction orchestration, authorization/ownership checks,
routers, statistics endpoints, and CSV export are Stage 2 and are **not**
covered by this ADR yet — it will be extended, not replaced, when that
work lands.

## Context

Phase 4 requires a relational attendance schema and an audit trail that
records who marked or changed attendance and that also captures blocked
authorization attempts (`docs/IMPLEMENTATION_PLAN.md` Phase 4;
`docs/AUDIT.md` Critical finding C4; `docs/ARCHITECTURE.md` §6, §8). This
stage builds the schema, stable domain errors, Pydantic request/response
shapes, and repositories that Stage 2's service layer will orchestrate
inside transaction boundaries (`app/db/transaction.py`'s
`service_transaction`, already established in Phase 3).

## Decisions

1. **Attendance uniqueness rule.** One `attendance_records` row per
   `(student_profile_id, classroom_id, subject_id, attendance_date)`,
   enforced by an explicit four-column database `UNIQUE` constraint
   (`uq_attendance_records_student_classroom_subject_date`), not just an
   application-layer check. Stage 2's service layer is expected to
   upsert (update-if-exists) rather than rely on this constraint firing
   in normal operation; the constraint remains a structural backstop
   against a concurrent duplicate insert.

2. **Status enum.** `attendance_status` is a native PostgreSQL enum
   limited to `present` / `absent`, matching the `user_role` /
   `day_of_week` / `announcement_audience` pattern already established in
   Phase 2/3 — an invalid status is structurally impossible to store, not
   just application-validated. No `late`/`excused`/other status is added:
   nothing in `docs/IMPLEMENTATION_PLAN.md` Phase 4 calls for it, and
   adding one now would be unrequested scope creep.

3. **Maximum batch size.** A single bulk-attendance request is capped at
   200 student records (`app.modules.attendance.schemas.MAX_BULK_ATTENDANCE_ROWS`),
   enforced by the Pydantic schema (`Field(min_length=1, max_length=200)`)
   before any repository or database call. This is deliberately smaller
   than `app.modules.bulk_imports.parser.MAX_IMPORT_ROWS` (500): a
   bulk-attendance request is a synchronous, single-classroom operation
   (a realistic classroom roster is well under 200 students), not a
   background bulk-file import.

4. **No attendance-session table.** Neither `docs/IMPLEMENTATION_PLAN.md`
   Phase 4 nor `docs/ARCHITECTURE.md` describes a "session" concept
   distinct from the (classroom, subject, date) triple already captured
   by `attendance_records`. The simplest schema that satisfies every
   documented Phase 4 acceptance criterion is chosen instead of inventing
   an unrequested abstraction layer.

5. **Immutable audit-log design.** `audit_logs` has no `updated_at`
   column, and `app.modules.attendance.repository.AuditLogRepository`
   deliberately exposes only `create`, `get_by_id`, `list`, and `count` —
   no `update`/`delete`/`patch` method exists anywhere in the
   application for this model. This is verified by a structural
   regression test
   (`app.tests.test_audit_log_repository.test_audit_log_repository_has_no_update_or_delete_method`),
   not merely by omission.

6. **`actor_user_id` is non-nullable.** Every code path that will create
   an audit-log row (Stage 2) is only reached after authentication has
   already succeeded (Phase 2's `get_current_active_user` dependency) —
   there is no genuine Stage 1/2 case where the acting user is unknown.
   The Phase 4 brief's "nullable only when genuinely necessary" guidance
   therefore resolves to "not nullable" here. Both `actor_user_id`
   (`audit_logs`) and `marked_by_user_id` (`attendance_records`) use
   `ondelete="RESTRICT"` against `users`, matching
   `Announcement.author_user_id`'s existing rationale
   (`app/modules/announcements/models.py`): an attributable historical
   record must not be silently orphaned by a hard user deletion. In
   practice users are only ever soft-deactivated, never hard-deleted, so
   this is a structural backstop, not an expected code path.

7. **`audit_logs.classroom_id` / `subject_id` use `ondelete="SET NULL"`.**
   These are optional contextual-scope columns on an audit row, not part
   of its identity — losing the reference should not cascade into
   deleting audit history.

8. **Sanitized JSONB metadata column, named `event_metadata`.** The
   column is named `event_metadata` rather than `metadata` because
   `metadata` is reserved by SQLAlchemy's `DeclarativeBase`
   (`app/db/base.py`). It defaults to `{}` (`server_default='{}'::jsonb`)
   and is populated exclusively by Stage 2's service layer with
   pre-sanitized, size-bounded content. Stage 1 defines the column and
   its default only; no sanitization logic exists yet since no service
   layer writes to it in this stage.

9. **Repository transaction boundaries.** Both repositories in this
   stage follow the exact convention already established in
   `app.modules.academics.repository`: every write calls `flush()`, never
   `commit()`; `IntegrityError`s are caught, the session is rolled back,
   and a stable domain error is raised in their place (currently only
   `AttendanceRecordAlreadyExistsError`, since the migration's own FK
   constraints are the only other integrity path and Stage 1 does not yet
   have a service layer to validate references before calling `create`).
   Commit/rollback ownership remains entirely with the caller — Stage
   2's service layer, via `service_transaction`.

10. **Migration revision and parent.** New revision `e1208296dad5`,
    parent `32819e0a6027` (Phase 3 head, immutable and unedited).
    `downgrade()` drops `audit_logs` then `attendance_records` then both
    enums, landing back exactly at Phase 3 head with every Phase 1-3
    table and enum untouched.

## Consequences

- Stage 2 can build directly on these repositories without redefining
  filtering, aggregation, or persistence primitives — `aggregate_counts`
  already returns `(total, present, absent)` via a single `FILTER
  (WHERE ...)` query rather than three round trips or an in-Python
  scan.
- No authorization/ownership-check errors are defined yet
  (`app.modules.attendance.errors` only covers uniqueness/not-found/
  date-range concerns). Stage 2 must add scope-denial errors (teacher
  ownership, student self-service) before any router exists, per the
  Phase 4 brief's own explicit "out of scope" instruction for this
  stage.
- No service layer, router, CSV export, or blocked-audit-logging
  behavior exists yet. A request cannot reach this code through HTTP at
  all in Stage 1 — every test in this stage calls the repositories
  directly (mirroring `app.tests.test_academics_repository`'s
  established pattern), not through `client_db`.
- The 200-record batch cap is enforced only by the Pydantic schema so
  far; Stage 2's service layer must still perform its own
  pre-transaction validation (duplicate rejection, reference/active
  checks, ownership) before opening any write transaction, exactly as
  `docs/IMPLEMENTATION_PLAN.md` Phase 4 requires.

## Addendum: Stage 2 decisions (attendance service, authorization, audit)

## Status

Accepted for Stage 2 (`AttendanceService`, `BlockedAuditWriter`,
authorization errors). Stage 1's status/decisions above are unchanged;
this addendum only records what Stage 2 actually implemented. Routers,
CSV export, and statistics/detail/daily endpoints remain Stage 3 and are
not covered here.

## Stage 2 decisions

11. **Batch-level, not per-record, success audit.** One `AuditLog` row
    (`outcome=success`) is written per `bulk_save` call, not one per
    attendance record. A 200-record batch producing 200 audit rows would
    make the audit trail itself the dominant write cost and provide no
    additional forensic value over one row summarizing the batch
    (`created_count`/`updated_count`/`total_count`/bounded `record_ids`).

12. **Bounded, sanitized `event_metadata`.** Both the success and blocked
    audit paths write only pre-defined, safe keys —
    never raw remarks, request bodies, tokens, cookies, passwords, or
    exception strings. Success metadata: `attendance_date`,
    `created_count`, `updated_count`, `total_count`, `record_ids`
    (stringified, truncated to the first 50 via `_AUDIT_MAX_RECORD_IDS`),
    and `record_ids_truncated`. Blocked metadata: `reason_code` (one of
    three safe, non-identifying constants) and `attempted_action`.
    `classroom_id`/`subject_id`/`request_id`/`actor_user_id`/`action`/
    `outcome` are the dedicated `AuditLog` columns already defined in
    Stage 1 — not duplicated into the metadata blob.

13. **Blocked-audit writes use a fully independent transaction.**
    `BlockedAuditWriter` opens a brand-new `AsyncSession` from
    `async_sessionmaker(bind=get_engine(settings))` — the same shared,
    cached engine (keyed by `Settings.DATABASE_URL`) the rest of the
    application uses, not an ad hoc connection — writes one row, commits,
    and closes. This is deliberately never the caller's own
    `service_transaction`-bound session: a blocked scope is detected
    before any attendance write happens in Stage 2, so the main
    transaction has nothing to commit anyway, but reusing it would still
    couple an audit guarantee to an unrelated transaction's fate. A
    documented, narrow `try/except Exception` around this call ensures
    that if the independent write itself fails, the original
    `AttendanceScopeNotFoundError` is still raised (never replaced by
    the audit-write's own exception) — see
    `docs/HANDOVER_PHASE_4_STAGE_2.md`'s "Genuine review findings."

14. **Concealed unrelated-teacher-scope, unified into one error.**
    `AttendanceScopeNotFoundError` (404) is raised for every flavor of
    teacher-scope denial — missing/inactive teacher profile,
    non-existent classroom/subject, or missing/inactive assignment —
    rather than a distinct error per case. This reuses the concealment
    convention already established in `app.modules.auth.authorization`
    (an unrelated/denied object must be indistinguishable from a
    genuinely missing one to the client). The real reason is recorded
    only server-side, in the blocked audit row's `reason_code`.

15. **Ownership is always the authenticated actor, never client input.**
    `marked_by_user_id` (attendance rows) and `actor_user_id` (both audit
    outcomes) are set exclusively from `current_user.id`, the parameter
    the caller (a future router's `get_current_active_user` dependency)
    supplies. No field on `BulkAttendanceRecordIn`/`BulkAttendanceRequest`
    carries an actor, role, or marked-by value at all — there is
    structurally nothing for the service to accidentally trust from
    request data on this point.

## Addendum consequences

- Stage 3's routers can call `AttendanceService.bulk_save` directly with
  `current_user` (from `get_current_active_user`) and `request_id` (from
  `request.state.request_id`) — no further authorization wiring is
  needed at the router layer beyond a `require_roles(ADMIN, TEACHER)`
  dependency for the HTTP-level 403.
- `AttendanceRepository.aggregate_counts`/`list`/`count` (delivered in
  Stage 1) remain unused by any service until Stage 3's
  statistics/detail/daily endpoints are built.
- No new tables, columns, or migrations were needed for Stage 2 — every
  decision above is service-layer orchestration over Stage 1's existing
  schema.

## Addendum: Stage 3 decisions (reads, statistics, CSV export, audit-log API)

## Status

Accepted for Stage 3 (`AttendanceReadService`, the attendance/audit-log
routers, `csv_export.py`). Stage 1/2's status/decisions above are
unchanged; this addendum only records what Stage 3 actually implemented.

## Stage 3 decisions

16. **One shared `authorize_scope` method for every read/export
    endpoint**, deliberately mirroring Stage 2's `bulk_save` write-scope
    check rather than a separate, looser read-side rule. Admin's read
    access is restricted to *active* classrooms/subjects — the same
    restriction as the write path, not a broader "admin sees
    everything, active or not" allowance. This keeps read and write
    authorization symmetrical and avoids an undocumented second rule.

17. **Assigned-teacher authorization requires the exact classroom +
    subject pair**, not just "any classroom this teacher touches." A
    `TeacherAssignment` row must exist, be active, and match both IDs —
    the same shape Stage 2 already established for `bulk_save`, reused
    (not loosened) for reads.

18. **Concealed unrelated-teacher scope, reused for every read/export
    endpoint.** The same `AttendanceScopeNotFoundError` (404) Stage 2
    defined is raised for every flavor of read-side denial too —
    missing/inactive teacher profile, non-existent classroom/subject, or
    missing/inactive assignment are never distinguished in the response.

19. **Independent blocked-audit for every denied detail/daily/stats/
    export attempt**, reusing Stage 2's `BlockedAuditWriter` unchanged
    (own session/transaction, `outcome=blocked`, safe `reason_code`,
    real `request_id`, never the raw exception or request body). Four
    new action strings distinguish which read operation was denied:
    `attendance.read_detail`, `attendance.read_daily`,
    `attendance.read_stats`, `attendance.export`. No success audit is
    written for reads/exports — only `bulk_save` writes a success row;
    adding one for every read was not requested and would make read
    traffic the dominant audit-log write source for no stated benefit.

20. **`AttendanceReadService` does not call or modify Stage 2's private
    `AttendanceService._authorize_teacher_scope`.** That method is
    reserved for the `bulk_save` write path per Stage 2's own "Must NOT
    be redone" list. `AttendanceReadService` has its own, separately
    implemented `_authorize_teacher_scope` (same concealment outcome,
    distinct Stage-3-only reason-code constants). A deliberate trade:
    a small amount of structural duplication between two private
    methods in two different classes, in exchange for never touching
    Stage 2's already-reviewed `service.py` for an unrelated concern.
    Every read/export router endpoint still calls only this one Stage 3
    method — authorization is not duplicated per route.

21. **`classroom_id`/`subject_id` are required (non-optional) query
    parameters on every general read/export endpoint**, for both admin
    and teacher. Necessary to reuse one exact-scope authorization shape
    uniformly across roles, and it keeps statistics/detail from
    becoming an unbounded, Phase-8-style cross-classroom rollup — every
    request is one exact scope.

22. **SQL aggregation for every statistics query, never an in-Python
    scan.** `aggregate_by_student`/`aggregate_by_classroom` use the same
    single-query `FILTER (WHERE ...)` technique Stage 1's
    `aggregate_counts` already established — one `GROUP BY` query
    returns every row's `(total, present, absent)` triple directly from
    PostgreSQL.

23. **Three statistics grouping modes: `overall` (default), `student`,
    `classroom`.** `AttendanceStatsResponse` is one schema for all
    three — exactly one of `overall`/`by_student`/`by_classroom` is
    populated per response, rather than three separate response models
    or routes. No ranking, defaulter classification, leaderboard,
    trend, or prediction is implemented — that is explicitly Phase 8
    scope and was deliberately not touched here.

24. **`attendance_percentage` is always `round(present / total * 100,
    2)`; zero matching records is explicitly `0.0`**, never a division
    error or `null`. `present_count + absent_count` always equals
    `total_count`, structurally (both are `FILTER` aggregates over the
    same row set as the total), not just by convention.

25. **Student self-service is entirely identity-derived.**
    `_resolve_own_student_profile` reads `current_user.id` only; neither
    `/attendance/me/detail` nor `/attendance/me/stats` has a
    `student_profile_id` parameter on its function signature at all. A
    missing/inactive own profile raises `StudentProfileNotFoundError`
    (404) — the same self-profile error convention already established
    in `app.modules.profiles.student_service.StudentProfileService
    .get_for_user`, not a new error type invented here.

26. **In-memory CSV generation, never a temporary file.** The entire
    document is built in one `io.StringIO` buffer via the
    standard-library `csv` module. Column order is fixed:
    `attendance_date`, `classroom_code`, `subject_code`,
    `student_profile_id`, `student_roll_number`, `status`, `remarks`,
    `marked_by_user_id`, `created_at`, `updated_at`. `classroom_code`/
    `subject_code` come from the already-authorized `Classroom`/
    `Subject` (constant for one export request), not re-joined per row.
    An empty result still returns a valid CSV with only the header row.

27. **Apostrophe-prefix formula-injection escaping.** Any text cell
    beginning with `=`, `+`, `-`, or `@` is prefixed with a single
    leading apostrophe (`'`) before being written — the standard,
    widely-supported spreadsheet convention for forcing literal-text
    interpretation. Applied to `remarks` (the genuinely free-text field)
    and, defensively, to `student_roll_number` (admin-entered, not
    currently constrained to a strict character set).

28. **The export filename is server-controlled, built only from
    already-authorized classroom/subject codes**, with any character
    outside `[A-Za-z0-9_-]` defensively replaced by `_` — never derived
    from client input, and never a filesystem path.

29. **Audit-log reads are admin-only, with no extra service layer.**
    `audit_router.py` calls `AuditLogRepository` (Stage 1, unmodified)
    directly, since the only authorization rule is "caller's role is
    admin" — already enforced by the router's own `require_roles`
    dependency. No service class was introduced solely to wrap
    zero-authorization-complexity repository calls.

30. **Audit logs remain structurally append-only.** No `POST`/`PUT`/
    `PATCH`/`DELETE` route exists for `/audit-logs` anywhere, and
    `AuditLogRepository` has no `update`/`delete` method to call even by
    mistake — the append-only guarantee from Stage 1 is unchanged and
    unweakened by adding read routes.

## Stage 3 addendum consequences

- Phase 4 Stage 4 (final integration) can now run the full Docker/pytest
  gate against every endpoint this ADR's Stage 1–3 decisions describe,
  including the object-level authorization behavior that is this
  phase's concrete fix for `docs/AUDIT.md` Critical finding C4.
- No new tables, columns, or migrations were needed for Stage 3 either
  — every decision above is application-layer (repository query
  extensions, service orchestration, routers) over Stage 1's existing
  schema and Stage 2's existing service.
- Phase 8 (reports/analytics/leaderboards) remains untouched; nothing
  in Stage 3's statistics endpoint should be read as a precedent for
  building ranking/dashboard features directly into
  `AttendanceReadService` later — that is explicitly out of scope here
  and was kept out deliberately.

