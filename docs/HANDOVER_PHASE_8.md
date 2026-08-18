# Phase 8 Handover - Reports, Exports, and Analytics

**Status:** COMPLETE on 2026-08-17  
**Next phase:** Phase 9, NOT STARTED

## Scope delivered

Phase 8 rebuilds the legacy attendance-reporting surface on the authoritative
FastAPI/PostgreSQL backend and the Phase 7 React/TypeScript role shells. It
delivers bounded attendance reports, low-attendance defaulters, a classroom
leaderboard, report-specific CSV and PDF exports, and one Reports workflow for
Admin and Teacher. Student arbitrary-report access is deliberately absent.

Phase 7 announcements and attendance workflows were not reimplemented. No
database migration was required. Phase 9 deployment, CI, and final hardening
work has not started.

## Legacy parity audit and deliberate corrections

The Phase 8 kickoff inspected the legacy reports router/service and the actual
`backend_v2` attendance, profile, academic, authorization, and schema contracts.
The resulting parity decisions were:

| Legacy surface | Phase 8 result |
|---|---|
| Attendance report | Typed bounded summary plus deterministic detail rows. |
| Defaulters | Active roster is authoritative; students with no attendance records are included at `0.0%`; exactly-threshold students are not defaulters. |
| Classroom leaderboard | One set-based active-roster aggregate; stable percentage-descending, roll-number-ascending, UUID-ascending tie breaking. |
| CSV | Existing Phase 4 raw `/attendance/export` remains unchanged; Phase 8 adds a filter-matching report CSV. |
| PDF | Generated in memory with bounded data, repeated headers, and multiple pages; no legacy temporary-file pattern. |

The shared percentage contract is now one function:

`round(present_count / total_count * 100, 2)`, with `0.0` when the total is zero.

## Backend API contracts

All paths are under `/api/v1`, require Admin or Teacher, require an exact
`classroom_id` and `subject_id`, and reuse
`AttendanceReadService.authorize_scope`:

- `GET /reports/attendance`
- `GET /reports/defaulters`
- `GET /reports/leaderboard`
- `GET /reports/attendance/export.csv`
- `GET /reports/attendance/export.pdf`

Every endpoint requires either strict `month=YYYY-MM` or both `date_from` and
`date_to`. The two period forms cannot be mixed. An inclusive period is limited
to 366 days. The attendance report and both exports accept an optional active
roster `student_profile_id`. Defaulters accept `threshold` from 0 through 100,
defaulting to 75.

Teacher denial retains the existing concealed `404` contract and blocked audit
record. Admin retains the existing active academic-reference rules. The router
also role-gates every endpoint, so Student receives `403` and has no report
route in the frontend.

## Query, roster, and result semantics

- Attendance summary and detail are constrained to active students currently
  in the requested classroom, even if an inactive or moved student has
  historical attendance in the period.
- Defaulters and leaderboard start from the active roster with a left join to
  the period's attendance records. Zero-record students are therefore present,
  not accidentally omitted.
- Defaulters use the strict comparison `attendance_percentage < threshold`.
- Leaderboard ordering is percentage descending, roll number ascending with
  nulls last, then student-profile UUID ascending. Rank values follow that
  deterministic order.
- The roster aggregate is one grouped SQL statement. A focused SQLAlchemy
  statement-count test proves it performs one `SELECT`, not one query per
  student.
- Attendance details are capped at 5,000 rows; active-roster aggregate reports
  are capped at 1,000 students.

No ORM model or migration changed.

## Export behavior

The report CSV has the stable columns:

`attendance_date,student_profile_id,roll_number,status,remarks`

It uses exactly the attendance report's scope, period, and optional student
filter. Empty results produce the header row only. Roll numbers and remarks
beginning with `=`, `+`, `-`, or `@` are prefixed with an apostrophe to prevent
spreadsheet formula execution. The filename is derived only from authorized,
normalized classroom/subject codes and the resolved period.

The PDF uses ReportLab from the declared `reportlab>=4.2,<5.0` dependency. It
contains the authorized classroom/subject, period, summary, and the same detail
rows, repeats headers across pages, truncates cells to bounded single-line
text, and writes only to `io.BytesIO`. Both export routes send an attachment
`Content-Disposition`; the PDF uses `application/pdf` and CSV uses `text/csv`.

The pre-existing Phase 4 `GET /attendance/export` behavior and tests remain
unchanged and passing.

## Frontend workflow

Admin and Teacher now have `/admin/reports` and `/teacher/reports` routes,
navigation entries, and dashboard links. Student has neither a Reports route
nor navigation entry.

The page uses React Hook Form and Zod for:

- server-provided classroom and subject choices;
- active roster student choice for attendance detail/exports after an exact
  scope is selected (defaulters and leaderboard remain classroom-wide);
- month or explicit bounded date-range selection;
- a 0-100 defaulter threshold.

Report requests remain disabled until valid filters are submitted. The page
renders four summary metrics, deterministic detail rows, defaulters, and the
leaderboard, with explicit loading, empty, validation, server-error, and
download states.

The existing `ApiClient` gained a typed binary `download` method. It uses the
same credentialed request path and preserves the central contract: one refresh
and one retry after 401, no refresh after 403. Downloads honor the safe server
filename. The page creates one object URL, clicks a temporary anchor, removes
the anchor, and revokes the object URL in `finally`.

## Security and privacy closure

The final source scan confirmed:

- exact classroom-and-subject authorization is reused, not duplicated;
- no Student arbitrary report endpoint or route exists;
- there is no institution-wide student or biometric lookup;
- no biometric sample, embedding, image, candidate, credential, token, hash,
  or storage path is included in a report response or export;
- no report/export code writes a temporary file;
- CSV formula triggers are escaped;
- filenames are normalized and server-controlled;
- no `localStorage`, `sessionStorage`, IndexedDB, axios, XMLHttpRequest,
  scattered fetch transport, auth/blob console logging, `any`, TypeScript
  suppression, or broad ESLint disable was added;
- the only frontend `fetch` calls remain inside `api/client.ts`;
- every report object URL is revoked.

## Verification evidence

Backend verification used the isolated PostgreSQL test service; no development
or production database was used.

- Focused Phase 8 plus attendance regressions: **48 passed**.
- Complete backend suite: **706 passed, 0 failed, 0 skipped**, with 13 existing
  deprecation/user warnings.
- Direct PostgreSQL spot check: an independent `COUNT(*)` matched the returned
  attendance summary total.
- Set-based query check: active-roster aggregation issued exactly one SELECT.
- Ruff format: all **13 Phase 8-touched Python files** already formatted.
- Ruff lint: all Phase 8-touched Python files passed.
- Strict mypy: **11 Phase 8 production source files** passed; router
  registration passed separately with historical imports skipped.
- Whole-app `compileall`: passed.
- Fresh Docker test target: built successfully; dependency resolution installed
  ReportLab 4.5.1 within the declared range.
- Focused tests in the fresh image: **48 passed**.

The full-tree Ruff/mypy baselines still contain documented historical Phase 5
debt under the current toolchain (14 old files would reformat, 23 old lint
findings, and historical strict-test typing findings). Those files were not
rewritten as part of Phase 8. No Phase 8 formatting, linting, or production
typing defect remains.

Frontend verification:

- `npm run typecheck`: passed.
- `npm run build`: passed with Vite 8.2.1; 126 modules transformed.
- `npm test -- --run`: **8 files, 40 tests passed**.
- `npm run lint`: passed with zero errors or warnings.
- `npm audit --audit-level=high`: **0 vulnerabilities**.

Focused coverage includes exact API query strings, role routing, no request
before valid submission, month and date-range filters, displayed report data,
leaderboard order, server errors, downloads and object-URL revocation, binary
401 refresh/retry, and binary 403 no-refresh behavior.

## Files added

- `backend_v2/app/modules/attendance/calculations.py`
- `backend_v2/app/modules/reports/__init__.py`
- `backend_v2/app/modules/reports/csv_export.py`
- `backend_v2/app/modules/reports/errors.py`
- `backend_v2/app/modules/reports/pdf_export.py`
- `backend_v2/app/modules/reports/repository.py`
- `backend_v2/app/modules/reports/router.py`
- `backend_v2/app/modules/reports/schemas.py`
- `backend_v2/app/modules/reports/service.py`
- `backend_v2/app/tests/test_reports_http.py`
- `frontend/src/api/reports.test.ts`
- `frontend/src/api/reports.ts`
- `frontend/src/pages/ReportsPage.test.tsx`
- `frontend/src/pages/ReportsPage.tsx`
- `docs/HANDOVER_PHASE_8.md`

## Files modified

- `backend_v2/app/api/router.py`
- `backend_v2/app/modules/attendance/csv_export.py`
- `backend_v2/app/modules/attendance/read_service.py`
- `backend_v2/pyproject.toml`
- `backend_v2/README.md`
- `frontend/src/api/client.test.ts`
- `frontend/src/api/client.ts`
- `frontend/src/api/queryKeys.ts`
- `frontend/src/app/App.test.tsx`
- `frontend/src/app/App.tsx`
- `frontend/src/layouts/RoleLayout.tsx`
- `frontend/src/pages/AdminDashboard.tsx`
- `frontend/src/pages/TeacherDashboard.tsx`
- `frontend/src/routes/config.ts`
- `frontend/src/styles.css`
- `frontend/src/types/domain.ts`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md`

The required frontend build regenerated `frontend/dist`; that generated folder
is excluded from the cumulative source artifact, matching Phase 7 packaging.
No source file was deleted.

## Deferred work and Phase 9 starting point

Phase 9 may begin from this closure record. Its existing plan remains CI,
deployment, final security hardening, and the authoritative README/API docs
rewrite. It must not redo Phase 8 reports or exports.

No Git operation was performed.

**Phase 8 COMPLETE. Phase 9 NOT STARTED.**
