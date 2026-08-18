# Phase 7 Handover - Admin, Teacher, and Student Workflows

**Status:** COMPLETE on 2026-08-16  
**Next phase:** Phase 8, NOT STARTED

## Scope delivered

Phase 7 replaces the Phase 6 placeholder routes with contract-backed workflows
for all three application roles. Server state is managed through TanStack Query,
forms use React Hook Form with Zod validation, and every HTTP operation goes
through the existing typed `ApiClient`.

Phase 5 and Phase 6 history remains authoritative in the earlier handovers.
Phase 7 did not start reports, exports, analytics, deployment, or CI work.

## Integration blocker and approved backend correction

The initial frontend contract audit found one concrete blocker. Manual first-time
attendance and recognition confirmation both require a
`student_profile_id`, but:

- the general student-profile listing is admin-only;
- daily attendance cannot include students who have never been marked;
- recognition results intentionally do not expose their internal candidate
  snapshot; and
- using attendance history, arbitrary client IDs, or institution-wide search
  would weaken authorization and privacy.

After the blocker was reported, one narrow Phase 7 backend correction was
explicitly authorized:

`GET /api/v1/attendance/roster?classroom_id=<uuid>&subject_id=<uuid>`

The endpoint returns a dedicated minimal response containing only
`student_profile_id` and `roll_number`.

The roster is derived server-side from active classroom membership. It reuses
`AttendanceReadService.authorize_scope`, so an admin follows existing admin
semantics and a teacher must have the exact active classroom-and-subject
assignment. There is no institution-wide fallback. An authorized empty
classroom returns `[]`. The read does not write attendance and exposes no
biometric data, embeddings, recognition candidates, credentials, or storage
paths.

Backend files changed for this approved correction:

- `backend_v2/app/modules/attendance/router.py`
- `backend_v2/app/modules/attendance/schemas.py`
- `backend_v2/app/modules/attendance/read_service.py`
- `backend_v2/app/tests/test_attendance_roster_http.py` (added)

No migration was required. No recognition algorithm, enrollment behavior,
attendance write semantics, authentication architecture, or unrelated backend
behavior was changed.

## Admin workflows

The admin workspace now provides:

- classroom create, list, edit, pagination, and soft deactivation;
- subject create, list, edit, elective status, pagination, and soft
  deactivation;
- teacher-profile create, list, edit, pagination, and soft deactivation;
- student-profile create, list, classroom-membership update, pagination, and
  soft deactivation;
- exact teacher/classroom/subject assignment create, active-state update, list,
  pagination, and soft deactivation;
- timetable create, list, edit, time-order validation, pagination, and soft
  deactivation;
- announcement create, list, edit, audience/classroom targeting, and soft
  deactivation;
- CSV/XLSX bulk import for classrooms, subjects, teacher profiles, and student
  profiles, including supported-extension and 2 MiB checks plus structured
  row-error display.

Teacher and student profile creation accepts an existing user UUID because the
current backend exposes profile management, not user-account provisioning.

## Teacher workflows

The teacher workspace now provides:

- current teacher profile summary;
- server-scoped classrooms, subjects, and timetable entries;
- a detailed class/timetable view;
- manual attendance using the new server-authorized roster;
- recognition attendance using camera capture or an image-file fallback;
- role-visible announcements.

The server remains authoritative for every classroom/subject authorization
decision. A combination that is not an exact authorized scope is rejected by
the roster/attendance backend.

## Student workflows

The student workspace now uses only self-service contracts and provides:

- current student profile and roll-number summary;
- own attendance totals, present/absent counts, and percentage;
- own detailed attendance records;
- optional classroom, subject, date-range, and status filters;
- role/classroom-visible announcements.

It does not call the admin student list or accept a student ID for self-service
attendance.

## Manual attendance behavior

The teacher selects a classroom, subject, and date. The UI loads both the
authorized active roster and any existing daily records. Existing statuses are
preserved; students without a saved record default to absent until the teacher
changes them. The UI sends one `POST /api/v1/attendance/bulk` request containing
only roster-provided `student_profile_id` values. Query caches are invalidated
only after a successful save, and a failed save cannot display a success
message.

## Recognition camera and file behavior

The recognition form sends the backend's exact multipart fields to
`POST /api/v1/face-recognition/attendance/attempts`: `classroom_id`,
`subject_id`, `attendance_date`, and `file`.

The UI supports direct `getUserMedia` capture and a normal JPEG/PNG/WebP file
fallback. Captures remain only in component memory long enough to submit. No
object URL is created. Starting a replacement stream, pressing stop, capturing,
or leaving the page stops all `MediaStream` tracks.

Decision behavior is explicit:

- **FOUND:** the backend has already written attendance. The UI invalidates
  attendance queries and never sends a second bulk/direct attendance write.
- **UNKNOWN:** no attendance is written automatically. The UI loads only the
  exact authorized roster and requires explicit teacher confirmation.
- **AMBIGUOUS:** identical safe confirmation behavior to UNKNOWN; there is no
  automatic write or institution-wide search.

Confirmation sends only `{ "student_profile_id": "..." }` to
`POST /api/v1/face-recognition/attendance/attempts/{attempt_id}/confirm`.

## Integrated Phase 7 API contracts

Admin and shared contracts:

- `GET/POST/PATCH/DELETE /api/v1/classrooms`
- `GET/POST/PATCH/DELETE /api/v1/subjects`
- `GET/POST/PATCH/DELETE /api/v1/teacher-profiles`
- `GET/POST/PATCH/DELETE /api/v1/student-profiles`
- `PUT /api/v1/student-profiles/{id}/classroom-membership`
- `GET/POST/PATCH/DELETE /api/v1/teacher-assignments`
- `GET/POST/PATCH/DELETE /api/v1/timetable-entries`
- `GET/POST/PATCH/DELETE /api/v1/announcements`
- `POST /api/v1/imports/{entity}`

Teacher contracts:

- `GET /api/v1/teacher-profiles/me`
- role-scoped `GET /api/v1/classrooms`
- role-scoped `GET /api/v1/subjects`
- role-scoped `GET /api/v1/timetable-entries`
- `GET /api/v1/attendance/roster`
- `GET /api/v1/attendance/daily`
- `POST /api/v1/attendance/bulk`
- `POST /api/v1/face-recognition/attendance/attempts`
- `POST /api/v1/face-recognition/attendance/attempts/{attempt_id}/confirm`
- `GET /api/v1/announcements`

Student contracts:

- `GET /api/v1/student-profiles/me`
- `GET /api/v1/attendance/me/stats`
- `GET /api/v1/attendance/me/detail`
- `GET /api/v1/announcements`

## Frontend architecture additions

- Typed Phase 7 domain DTOs and resource-specific API modules.
- `ApiClient` support for `PUT`, `PATCH`, and `DELETE`, while preserving its
  centralized refresh/retry behavior and FormData handling.
- Role navigation and concrete routes for every delivered workflow.
- A reusable typed admin CRUD component with loading, empty, error, success,
  pagination, edit, and confirmation states.
- TanStack Query keys and mutation invalidation scoped by resource or attendance
  domain.
- Responsive forms, tables, cards, status controls, camera preview, and mobile
  navigation styles.

## Security and privacy closure

The final frontend source scan confirmed:

- no `localStorage`, `sessionStorage`, or IndexedDB token/image persistence;
- one in-memory auth token store and one established `ApiClient` transport;
- no axios, XMLHttpRequest, or scattered `fetch` client (the only `fetch` calls
  remain inside `api/client.ts`);
- no `any`, `@ts-ignore`, `@ts-expect-error`, or broad ESLint disable;
- no token, password, image, or blob console logging;
- no object-URL lifecycle to leak;
- no institution-wide student/recognition fallback;
- FOUND has no second attendance write path;
- UNKNOWN/AMBIGUOUS choices come only from the authorized roster endpoint;
- camera tracks are stopped on stop, replacement, capture, and unmount;
- no browser persistence of biometric images or embeddings.

The roster endpoint is server-derived, exact-scope authorized, read-only, and
returns no biometric material. RBAC was not weakened.

## Verification evidence

### Approved backend correction

The current source was bind-mounted into the already-built authoritative Phase
6 backend test image and run against the isolated PostgreSQL test service. A
fresh image rebuild was attempted first but timed out while rebuilding dlib; no
test result was claimed from that timeout.

- focused roster HTTP test file: **5 passed, 3 pre-existing Starlette warnings**
  in 9.90 seconds;
- roster plus existing attendance service and attendance HTTP regression set:
  **52 passed, 3 pre-existing Starlette warnings** in 77.95 seconds;
- Ruff format on four focused files: **4 files already formatted**;
- scoped Ruff lint: **all checks passed**;
- strict mypy on the three modified application files: **success, no issues in
  3 source files**;
- `compileall` with an external pycache prefix: **passed**;
- migration: **not required**.

### Frontend

- `npm run typecheck`: **passed** (`tsc --noEmit`, zero errors);
- `npm run build`: **passed** with Vite 8.2.1; 124 modules transformed;
- `npm test -- --run`: **6 test files, 28 tests passed**;
- `npm run lint`: **passed**, zero errors/warnings;
- `npm audit --audit-level=high`: **found 0 vulnerabilities**.
- lightweight post-closure route check after removing unused placeholders:
  `src/app/App.test.tsx` **1 file, 14 tests passed**.

Tests cover auth/role routing, the typed client, exact Phase 7 roster and
self-service URLs, recognition multipart field names, recognition confirmation
payloads, admin validation/create/edit/deactivation/invalidation, authoritative
manual roster loading and bulk payloads, failed-save messaging, FOUND no-double-
write behavior, UNKNOWN roster-only confirmation, and camera-track cleanup.

These are focused component/API tests with a mocked browser network boundary;
no live browser-to-FastAPI end-to-end test is claimed. The backend HTTP tests
used the PostgreSQL-backed Docker test environment described above.

## Files added, modified, and deleted

Backend files are listed in the blocker section above.

Frontend files added:

- `frontend/src/api/academics.ts`
- `frontend/src/api/announcements.ts`
- `frontend/src/api/attendance.ts`
- `frontend/src/api/errorMessage.ts`
- `frontend/src/api/imports.ts`
- `frontend/src/api/params.ts`
- `frontend/src/api/phase7.test.ts`
- `frontend/src/api/profiles.ts`
- `frontend/src/api/queryKeys.ts`
- `frontend/src/api/recognition.ts`
- `frontend/src/components/AdminCrudPage.tsx`
- `frontend/src/components/AdminCrudPage.test.tsx`
- `frontend/src/pages/Admin/AdminResourcePages.tsx`
- `frontend/src/pages/AdminImportsPage.tsx`
- `frontend/src/pages/AnnouncementsPage.tsx`
- `frontend/src/pages/ManualAttendancePage.tsx`
- `frontend/src/pages/ManualAttendancePage.test.tsx`
- `frontend/src/pages/RecognitionAttendancePage.tsx`
- `frontend/src/pages/RecognitionAttendancePage.test.tsx`
- `frontend/src/pages/StudentAttendancePage.tsx`
- `frontend/src/pages/TeacherSchedulePage.tsx`
- `frontend/src/types/domain.ts`

Frontend files modified:

- `frontend/src/api/client.ts`
- `frontend/src/app/App.tsx`
- `frontend/src/app/App.test.tsx`
- `frontend/src/layouts/RoleLayout.tsx`
- `frontend/src/pages/AdminDashboard.tsx`
- `frontend/src/pages/StudentDashboard.tsx`
- `frontend/src/pages/TeacherDashboard.tsx`
- `frontend/src/routes/config.ts`
- `frontend/src/styles.css`

Frontend files deleted because their Phase 6 placeholders are no longer used:

- `frontend/src/pages/PhaseSevenPlaceholder.tsx`
- `frontend/src/pages/RoleDashboard.tsx`

Documentation files:

- `docs/HANDOVER_PHASE_7.md` (added)
- `docs/IMPLEMENTATION_PLAN.md` (updated)
- `docs/PROGRESS.md` (updated)

No dependency manifest or lock file changed. No Git operation was performed.

## Deferred work and exact Phase 8 starting point

Phase 8 has not started. Its starting point is the existing reports, exports,
and analytics scope: implement and verify report endpoints/UI, attendance
defaulters, classroom leaderboards, and CSV/PDF exports against authoritative
data. Phase 7 announcements are complete and must not be reimplemented.

Also deferred beyond this closure: live browser-to-backend role smoke tests,
the broader accessibility/polish pass, and real biometric model calibration.
No recognition accuracy claim is made by Phase 7.

**Phase 7 COMPLETE. Phase 8 NOT STARTED.**
