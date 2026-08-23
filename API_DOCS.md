# ShikshaSathi v2 API

This document summarizes the implemented FastAPI contracts. The generated
OpenAPI document at `/openapi.json` is authoritative for field-level schemas;
Swagger UI is at `/docs` when the backend is reached directly.

## Conventions

- Business API prefix: `/api/v1`
- Access authentication: `Authorization: Bearer <access_token>`
- Refresh authentication: rotating opaque token in a path-scoped HttpOnly
  cookie; JavaScript never reads it.
- Roles: `admin`, `teacher`, `student`; roles are reloaded from PostgreSQL on
  every authenticated request rather than trusted from a token claim.
- Pagination: `{"items": [...], "total": n, "limit": n, "offset": n}`
- Errors:

```json
{
  "error": {
    "code": "STABLE_ERROR_CODE",
    "message": "Client-safe message.",
    "details": {}
  },
  "request_id": "correlation-id"
}
```

Validation responses omit submitted values. Unexpected failures return a
generic 500 message; driver exceptions, stack traces, credentials, tokens,
biometric values, and filesystem paths are not returned.

## Health and service information

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| GET | `/` | None | Service name/version plus health links. |
| GET | `/health/live` | None | Process liveness; no database access. |
| GET | `/health/ready` | None | Real PostgreSQL `SELECT 1`; 503 when unavailable. |

The production frontend proxies `/health/*` to the internal backend.

## Authentication

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/login` | None | Email/password login; returns user + access token and sets refresh cookie. |
| POST | `/api/v1/auth/refresh` | Refresh cookie + same-origin check | Rotates refresh session and returns a new access token. |
| POST | `/api/v1/auth/logout` | Optional refresh cookie + same-origin check | Idempotently revokes/clears the current refresh session. |
| GET | `/api/v1/auth/me` | Access token | Safe current-user representation. |

Login is fixed-window rate-limited by client address. The default permits five
attempts per 60 seconds; a blocked request returns 429,
`RATE_LIMIT_EXCEEDED`, and `Retry-After` without recording credentials or the
request body.

Login request:

```json
{"email": "admin@example.com", "password": "your-password"}
```

No public registration endpoint exists. The first admin is created with
`python -m scripts.bootstrap_admin` after migrations.

## Academic resources

All routes require an access token. Admin has management access; teacher and
student reads are filtered by active database relationships. Unrelated private
objects are generally concealed as 404.

| Resource | Collection | Item | Notes |
|---|---|---|---|
| Classrooms | `GET, POST /api/v1/classrooms` | `GET, PATCH, DELETE /api/v1/classrooms/{classroom_id}` | Scoped list/read; admin create/update/soft-deactivate. |
| Subjects | `GET, POST /api/v1/subjects` | `GET, PATCH, DELETE /api/v1/subjects/{subject_id}` | Scoped list/read; admin create/update/soft-deactivate. |
| Teacher profiles | `GET, POST /api/v1/teacher-profiles` | `GET, PATCH, DELETE /api/v1/teacher-profiles/{profile_id}` | Admin list/write; owning teacher may read one. |
| Student profiles | `GET, POST /api/v1/student-profiles` | `GET, PATCH, DELETE /api/v1/student-profiles/{profile_id}` | Admin list/write; owning student may read one. |
| Assignments | `GET, POST /api/v1/teacher-assignments` | `GET, PATCH, DELETE /api/v1/teacher-assignments/{assignment_id}` | Exact teacher/classroom/subject assignment; admin only. |
| Timetable | `GET, POST /api/v1/timetable-entries` | `GET, PATCH, DELETE /api/v1/timetable-entries/{entry_id}` | Scoped reads; admin writes; slot/assignment validation. |
| Announcements | `GET, POST /api/v1/announcements` | `GET, PATCH, DELETE /api/v1/announcements/{announcement_id}` | Role/classroom visibility; admin writes. |

Additional profile routes:

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/v1/teacher-profiles/me` | Teacher | Own active profile. |
| GET | `/api/v1/student-profiles/me` | Student | Own active profile. |
| PUT | `/api/v1/student-profiles/{profile_id}/classroom-membership` | Admin | Assign, move, or unassign a student. |

DELETE operations above are soft deactivations, not hard row deletion.

## Academic bulk import

`POST /api/v1/imports/{entity}` is admin-only multipart upload for
`classrooms`, `subjects`, `teacher-profiles`, or `student-profiles`.

- Accepted: UTF-8 CSV and XLSX.
- Maximum: 2 MiB and 500 non-blank rows.
- Headers are strict; unknown/duplicate/missing columns reject the file.
- Expected row errors are returned with stable codes and row numbers; submitted
  row values and credentials are not echoed.
- Spreadsheet formulas are read only as cached values and never executed.

## Attendance and audit

| Method | Path | Role/scope | Purpose |
|---|---|---|---|
| POST | `/api/v1/attendance/bulk` | Admin or exact assigned teacher | Transactional create/update of one classroom/subject/date batch. |
| GET | `/api/v1/attendance/roster` | Admin or exact assigned teacher | Minimal active roster: student profile ID + roll number. |
| GET | `/api/v1/attendance/detail` | Admin or exact assigned teacher | Bounded filtered attendance rows. |
| GET | `/api/v1/attendance/daily` | Admin or exact assigned teacher | Exact classroom/subject/date records. |
| GET | `/api/v1/attendance/stats` | Admin or exact assigned teacher | Overall/student/classroom raw counts and percentages. |
| GET | `/api/v1/attendance/export` | Admin or exact assigned teacher | In-memory formula-safe raw CSV export. |
| GET | `/api/v1/attendance/me/detail` | Student | Caller-derived own rows; no arbitrary student ID parameter. |
| GET | `/api/v1/attendance/me/stats` | Student | Caller-derived own totals and percentage. |
| GET | `/api/v1/audit-logs` | Admin | Filtered paginated immutable audit events. |
| GET | `/api/v1/audit-logs/{audit_log_id}` | Admin | One audit event. |

Every general attendance read/write/export authorizes the exact active
`(classroom_id, subject_id)` scope. A teacher without the matching assignment
receives concealed 404 and the blocked attempt is independently audited.

## Biometric enrollment

Admin-only except the owning-student metadata read:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/biometric-enrollments/{student_profile_id}/samples` | Create first validated JPEG/PNG/WebP sample. |
| PUT | `/api/v1/biometric-enrollments/{student_profile_id}/samples/active` | Replace the active sample. |
| GET | `/api/v1/biometric-enrollments/{student_profile_id}` | Safe enrollment/sample metadata; never bytes/path/embedding. |
| DELETE | `/api/v1/biometric-enrollments/{student_profile_id}` | Request/finalize deletion lifecycle. |
| POST | `/api/v1/biometric-enrollments/{student_profile_id}/deletion/finalize` | Idempotently resume deletion. |
| POST | `/api/v1/biometric-enrollments/bulk` | Manifest-driven bounded ZIP enrollment. |
| GET | `/api/v1/biometric-enrollments/reconciliation/report` | Read-only DB/filesystem drift report. |

Bulk ZIP ingestion validates every member before extraction: traversal,
absolute/drive/UNC paths, symlinks, encryption, nesting, duplicates,
compression ratio, member count, and uncompressed size. It never calls
`extractall()`/`extract()` and never derives storage paths from uploaded names.

## Face recognition and recognition attendance

Admin processing/diagnostic routes:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/face-recognition/samples/{sample_id}/process` | Detect, align, embed, and persist one pending sample. |
| POST | `/api/v1/face-recognition/samples/{sample_id}/retry` | Retry a failed sample. |
| GET | `/api/v1/face-recognition/samples/{sample_id}/status` | Safe processing status. |
| POST | `/api/v1/face-recognition/samples/process-pending` | Bounded on-demand batch processing. |
| GET | `/api/v1/face-recognition/health` | Safe provider/model readiness. |
| POST | `/api/v1/face-recognition/match-probe` | Diagnostic candidate-scoped match; never attendance. |

Teacher recognition-attendance routes:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/face-recognition/attendance/attempts` | Exact-scope image attempt; `FOUND` writes via AttendanceService only. |
| POST | `/api/v1/face-recognition/attendance/attempts/{attempt_id}/confirm` | Explicitly confirm authorized roster member for UNKNOWN/AMBIGUOUS. |

Images and aligned crops are never returned. Embeddings are never returned or
logged. Candidate scope is server-derived from the active authorized roster;
there is no institution-wide matching fallback.

## Reports and exports

All report routes require Admin or exact assigned Teacher scope, exact
`classroom_id` and `subject_id`, and either `month=YYYY-MM` or both
`date_from` and `date_to`. The inclusive period is capped at 366 days.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/reports/attendance` | Summary + bounded deterministic detail; optional active-roster student. |
| GET | `/api/v1/reports/defaulters` | Active students strictly below threshold, including zero-record students. |
| GET | `/api/v1/reports/leaderboard` | Deterministic active-roster percentage ranking. |
| GET | `/api/v1/reports/attendance/export.csv` | Filter-matching formula-safe CSV. |
| GET | `/api/v1/reports/attendance/export.pdf` | Filter-matching bounded in-memory multi-page PDF. |

Attendance detail is capped at 5,000 rows and roster analytics at 1,000
students. Report/export responses contain no biometric material. Students have
no arbitrary report endpoint.

## Dashboard analytics

| Method | Path | Role/scope | Purpose |
|---|---|---|---|
| GET | `/api/v1/analytics/overview?days=7&date_to=YYYY-MM-DD` | Authenticated; identity-derived Admin, Teacher, or Student scope | Population/assignment context, marked-record attendance summary, equal-duration comparison, and bounded daily trend. `days` accepts only `7` or `30`; optional `date_to` anchors the current window and defaults to today. |

The endpoint accepts no classroom, teacher, or student scope identifier. Admins
receive school-wide active-resource context and up to three lowest recorded-
attendance classrooms; teachers receive only active assignment scope; students
receive only their own attendance. Attendance is present marked records divided
by all marked records. Missing or unmarked records are excluded.
