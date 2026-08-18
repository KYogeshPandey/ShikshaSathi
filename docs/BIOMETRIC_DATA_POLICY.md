# Biometric Data Policy (Face Recognition)

**Status: application policy, Rebuild Phase 5 Stage 1; updated for
accuracy in Stage 3.** This document governs how ShikshaSathi v2
(`backend_v2`) handles biometric data. Enrollment/storage (Stage 2) and
detection/alignment/embedding/matching (Stage 3) are both now
implemented — see `docs/HANDOVER_PHASE_5_STAGE_2.md` and
`docs/HANDOVER_PHASE_5_STAGE_3.md`. This policy was written ahead of
that code (Stage 1), specifically so Stage 2/3 would be built against
an already-reviewed policy rather than one written under time pressure
once real biometric data was at stake; the paragraphs below marked
"Stage 3 resolution" record where an earlier, prospective statement in
this document has now been confirmed or narrowed by the actual Stage 3
implementation — nothing below reverses an earlier commitment, only
confirms how it was kept.

## Scope and legal disclaimer

**This is an application-design policy, not legal advice.** It records
engineering and product decisions this codebase will enforce
structurally (storage location, retention, API exposure, audit
coverage). It is deliberately silent on jurisdiction-specific
requirements — e.g. which specific consent mechanism, data-protection
registration, or retention-period ceiling a particular country's or
state's student-biometric-data law requires — because those vary by
where a given school deployment operates and change independently of
this codebase. **Before any real deployment collects biometric data
from students, the deploying organization must obtain jurisdiction-
specific legal review**; nothing in this document should be read as
satisfying that review.

## What biometric data will be stored

Once Phase 5 Stage 3 implements a real provider, three kinds of
artifact are in scope:

1. **Raw enrollment images** — the photo(s) a student is enrolled with.
2. **Aligned face crops** — the detector's cropped/normalized output for
   a raw image (`app.modules.face_recognition.domain.NormalizedFaceInput`
   in code terms).
3. **Embeddings** — the numeric vector a face is reduced to for matching
   (`app.modules.face_recognition.domain.EmbeddingVector`).

### Retention decision for each artifact

- **Raw enrollment images:** retained only as long as needed to
  (re-)generate an embedding, per the retention period below. Not kept
  indefinitely "just in case" — an image whose embedding has already
  been generated and confirmed is a liability with no ongoing product
  need, not an asset.
- **Aligned face crops:** treated as a transient intermediate artifact
  of the detect→embed pipeline, not a first-class stored record.
  **Stage 3 resolution:** confirmed — `app.modules.face_recognition.alignment`'s
  output (`NormalizedFaceInput`) exists only in memory for the duration
  of one processing/match-probe call and is never written to disk or
  the database anywhere in the Stage 3 implementation. Only the raw
  enrollment image (Stage 2's own `biometric_samples` storage) and the
  final embedding (Stage 3's `biometric_embeddings` table) persist.
- **Embeddings:** the only artifact genuinely needed for ongoing
  matching. Retained for as long as the student's enrollment is active.
  **Stage 3 resolution:** persisted in a new `biometric_embeddings`
  table (migration `d22bce264ecd`), one row per successfully processed
  sample, `is_active`-flagged; a sample's embedding stops being usable
  for matching the moment the sample itself is no longer `ACTIVE`
  (deleted/quarantined/replaced) — enforced at the matching-candidate
  query level, see `docs/HANDOVER_PHASE_5_STAGE_3.md`, "Persistence
  design."

## Storage

- All biometric data — raw images, crops, and embeddings alike — is
  stored **outside the public web root**, at the path configured by
  `Settings.BIOMETRIC_STORAGE_ROOT` (`app/core/config.py`). That setting
  fails startup validation if pointed at an obviously public/static
  directory (e.g. any path segment named `static`, `public`, `www`,
  `wwwroot`, `frontend`, or `node_modules`) — a narrow, named-segment
  check, not a substitute for a real deployment review of the actual
  filesystem layout in production.
- Uploaded file names never determine storage paths. A future Stage 2
  enrollment endpoint must generate its own storage identifier (e.g. a
  UUID) rather than deriving a path from anything the client sent — the
  same class of fix `docs/AUDIT.md` §2.11/H4 already required for the
  legacy app's zip-slip-vulnerable bulk-photo import, applied here from
  the start rather than retrofitted.
- Biometric storage is excluded from routine backend backups/exports
  that are not specifically the biometric-data backup itself — i.e. a
  general database dump or code-repository export must not incidentally
  bundle raw biometric files. (`.gitignore` is updated in this
  checkpoint to exclude `backend_v2`'s future storage root from the
  repository itself — see `docs/HANDOVER_PHASE_5_STAGE_1.md`.)

## Identity linkage

- Every stored biometric artifact is linked to exactly one
  `app.modules.profiles.models.StudentProfile` — never a bare name,
  roll number, or classroom, which are guessable/reassignable identifiers,
  not a stable identity key. This mirrors the existing project convention
  of using `StudentProfile.id`/`user_id` as the authoritative identity
  reference everywhere else (e.g. `AttendanceRecord.student_profile_id`).
- The face-recognition provider layer itself never resolves or returns a
  `StudentProfile` object — only a `student_profile_id` (`uuid.UUID`),
  exactly like `app.modules.attendance`'s existing convention of passing
  IDs across layer boundaries rather than ORM instances. See
  `app/modules/face_recognition/domain.py`'s `MatchResult` and
  `app/tests/test_face_recognition_contracts.py`'s
  `test_end_to_end_fake_pipeline_never_returns_an_orm_model`.

## Who may enroll, read metadata, replace, and delete

(Roles below reuse the existing Phase 2 RBAC roles — `admin`, `teacher`,
`student` — and the existing Phase 3/4 ownership-check convention of
concealing another person's private record as a normal `404`, not a
distinguishable `403`.)

- **Enroll (create):** admin only, for any student. A teacher may not
  enroll a student's biometric data directly, even for a student in
  their own assigned classroom — enrollment is an identity-management
  action (like linking a `StudentProfile` to a `User`, which is also
  admin-only today), not a day-to-day teaching action.
- **Read metadata** (e.g. "is this student enrolled", enrollment
  timestamp) — admin, or the student themself for their own record only
  (mirroring `GET /student-profiles/me`'s existing self-service
  pattern). **Raw biometric data and embeddings are never returned by
  any metadata-read endpoint** — see "API response restrictions" below.
- **Replace** (re-enroll with a new photo) — admin only, same reasoning
  as enroll.
- **Delete** — admin only, plus the automatic deactivation-triggered
  deletion behavior described below. A student may request deletion of
  their own biometric data (a reasonable self-service right for
  sensitive personal data), but the actual deletion is still performed
  through the admin-owned deletion path, not a new student-facing
  destructive endpoint — consistent with students never having *any*
  destructive capability elsewhere in this codebase today (e.g. a
  student cannot deactivate their own `StudentProfile` either).
- **Teacher actions remain classroom/subject/assignment scoped where
  applicable** — e.g. a Stage 4 recognition-based attendance-marking
  action is still gated by the same teacher↔classroom ownership check
  Phase 4's `AttendanceService` already enforces (`docs/adr/0010`); a
  teacher's ability to *trigger* a recognition attempt for their own
  classroom is not the same permission as being able to enroll or
  inspect biometric data itself.
- **Admin override is explicit.** Wherever a check above would otherwise
  deny access, an admin's override is a distinct, logged code path (an
  audit-log `event_metadata` entry noting "admin override"), not a
  silent bypass indistinguishable from a normal allowed read.

## Consent and authorization assumptions

This project assumes institutional (school-level) authorization for
enrolling students' biometric data for attendance purposes is obtained
by the deploying school through its own enrollment/parental-consent
process, **outside this codebase**. This codebase's own responsibility
is limited to: (a) only ever storing/processing biometric data that was
deliberately submitted through the admin-only enrollment path (never
inferred or captured incidentally), and (b) implementing the technical
retention/deletion/access controls in this document faithfully. It does
not implement a consent-tracking or consent-withdrawal workflow itself
in Stage 1–5's scope — a deploying school that requires one must build
or procure it as a layer on top of, or a modification to, this design.

## Retention period and retention event

- **Retention period:** for as long as the linked `StudentProfile` is
  `is_active=True` and the student remains enrolled, plus a bounded
  grace window after deactivation (exact grace window is a Stage 2/3
  configuration decision, not fixed by this document — but it must be
  bounded, not indefinite).
- **Retention-triggering event:** biometric data is retained only while
  its enrollment reason still holds — an active student who needs
  attendance recognized. It is not retained "for analytics", "for model
  improvement", or any purpose beyond attendance recognition for that
  specific student.

## Enrollment, deletion, and replacement atomicity (mandatory Stage 2 architecture)

**Correction to an earlier draft of this policy:** a database transaction
(e.g. this codebase's existing `app/db/transaction.py` pattern, used for
Phase 4's attendance bulk-save) can only make **database writes**
atomic. It cannot, by itself, make a **filesystem** write or delete
atomic with a database change — a process crash or an unhandled
exception between "file written to disk" and "database row committed"
(or vice versa) can leave the two out of sync no matter how the
database side is wrapped. An earlier draft of this document
incorrectly implied that reusing `app/db/transaction.py` alone would
make biometric deletion atomic; it does not, and no Stage 1 code
depends on that claim being true (Stage 1 implements no enrollment,
deletion, or filesystem-writing code at all). This section replaces
that claim with the actual architecture Stage 2 must implement instead.

**None of the workflows below are implemented in Stage 1.** They are
documented here as a mandatory design constraint on Stage 2 (face
enrollment and secure photo ingestion, `docs/IMPLEMENTATION_PLAN.md`
Phase 5 Stage 2), so Stage 2 is built against an already-reviewed
consistency design rather than one improvised under time pressure once
real file writes are at stake.

### Enrollment (create)

1. **Write into a private temporary/staging path** — never directly into
   the final `BIOMETRIC_STORAGE_ROOT` location, and never a path derived
   from an uploaded filename (see "Storage" above).
2. **Validate, decode, and hash the staged file** before it is treated as
   trustworthy — confirming it actually decodes as an image of the
   expected kind, is within `Settings.MAX_ENROLLMENT_IMAGE_BYTES`, and
   recording a content hash for later integrity checks.
3. **Persist a `PENDING` database row** referencing the staged file's
   identifier — this is the one step a real database transaction *does*
   make atomic (the row either commits or it doesn't), but at this point
   the row and the staged file are still two separate resources, not one
   atomic unit.
4. **Atomically move/rename the staged file to its server-generated
   final path** — a filesystem rename within the same volume/filesystem
   is atomic at the OS level (unlike a multi-step copy-then-delete), which
   is the actual atomicity primitive this design relies on, not the
   database transaction.
5. **Transition the row to `ACTIVE`** only after the rename above has
   succeeded.
6. **Compensating cleanup and reconciliation for failures:** if the
   process crashes or errors between steps 3–5, the result is a
   `PENDING` row with no corresponding `ACTIVE` file (or a staged file
   with no corresponding row) — not a corrupted "half-enrolled" record
   masquerading as valid. A reconciliation job (run periodically, not
   inline with the request) sweeps `PENDING` rows older than a bounded
   timeout and either retries the move or deletes the stale row/staged
   file, and separately sweeps orphaned staged files with no matching
   `PENDING` row.

### Deletion / replacement

1. **Mark the row `DELETION_PENDING` or `REPLACEMENT_PENDING`** — a
   single, atomic database write; the artifact is not touched yet.
2. **Move the existing artifact into a private quarantine/staging
   location** where possible, rather than deleting it in place
   immediately — this keeps a recovery path open if the surrounding
   operation fails partway, and again relies on an atomic filesystem
   rename, not a database transaction, as the actual consistency
   primitive.
3. **Finalize the database state** (`DELETED`, or — for a replacement —
   `ACTIVE` pointing at the new artifact once its own enrollment steps
   above have completed).
4. **Purge the quarantined artifact asynchronously and retryably** — a
   background job, not an inline part of the request/response cycle, so
   a slow or failing filesystem delete cannot block or fail the
   user-facing operation. Retryable means a failed purge attempt is
   requeued, not silently dropped.
5. **Reconciliation for database/filesystem drift:** the same
   periodic reconciliation job from enrollment above also checks for
   quarantined artifacts with no corresponding `DELETION_PENDING`/
   `REPLACEMENT_PENDING` row (purge them) and rows stuck in a pending
   state past a bounded timeout (retry or escalate for manual review —
   never left pending indefinitely).

### What this means for Stage 1

No enrollment, deletion, replacement, staging, quarantine, or
reconciliation code exists anywhere in this checkpoint —
`app/modules/face_recognition/` contains only the typed contracts,
protocols, and errors described elsewhere in this document and in
`docs/HANDOVER_PHASE_5_STAGE_1.md`. This section is a design
requirement Stage 2 must satisfy, not a description of code that
already exists.

## Handling when a student/user is deactivated or deleted

- **Deactivation (`StudentProfile.is_active = False`, the existing
  Phase 3 soft-delete pattern):** biometric data is not immediately
  deleted (a deactivated student may be reactivated later — e.g. a
  transfer or a correction), but enters the bounded retention grace
  window described above rather than being retained indefinitely.
- **Hard deletion of the underlying `User`/`StudentProfile` row** (which
  Phase 2/3's own design notes describe as an edge case the codebase
  structurally guards against via `ondelete` behavior, not an expected
  operational path): any linked biometric data must be deleted as part
  of the same operation, never left as an orphaned artifact referencing
  a `student_profile_id` that no longer resolves to anyone.

## Audit requirements

Every one of the following is an auditable event once Stage 2+
implements it, reusing the existing Phase 4 `AuditLog` model/pattern
(`app.modules.attendance.models.AuditLog`) rather than inventing a
parallel audit mechanism:

- Enrollment (create)
- Replacement
- Deletion
- Every recognition *decision* — `FOUND`, `UNKNOWN`, and `AMBIGUOUS`
  alike, not just successful matches — mirroring Phase 4's existing
  requirement that blocked/denied attempts are audited, not only
  successful ones (`docs/adr/0010`).

Audit entries record *that* an action happened, who performed or
triggered it, and its outcome — never the raw biometric payload itself
(see "Logging restrictions" below).

## Backup / export exclusions

- A general-purpose database backup or a code/config export (e.g. this
  project's own delivered-ZIP convention, `docs/PROGRESS.md`'s
  pre-packaging audit step) must exclude biometric storage by default.
  Biometric data, if it needs to be backed up at all, is backed up
  through its own explicit, access-controlled mechanism — not swept up
  incidentally by an unrelated backup job.

## API response restrictions

- **Raw biometric data is never returned in list APIs.** A future
  student/teacher/admin list endpoint that includes enrollment status
  returns a boolean/timestamp at most — never image bytes, never a URL
  that resolves to the raw image, never the embedding.
- **Embeddings are never returned through normal application APIs**, to
  any role, under any circumstance — an embedding is not "the student's
  data to view" the way a profile field is; it is a biometric secret the
  application uses internally for matching only.
- **Matching results must not directly write attendance.** A recognition
  match is an input to a Stage 4 attendance-marking workflow, not itself
  an attendance write. Any actual attendance write reuses the existing
  Phase 4 `app.modules.attendance.service.AttendanceService` — the
  recognition/provider layer never touches `attendance_records` or
  `audit_logs` directly. This is a structural requirement carried over
  unchanged from the Stage 1 brief and repeated in
  `app/modules/face_recognition/__init__.py`.
- **Low-confidence/ambiguous results require confirmation.** A
  `MatchStatus.AMBIGUOUS` or `MatchStatus.UNKNOWN` result
  (`app.modules.face_recognition.domain.MatchResult`) must never be
  silently resolved to "closest guess" by Stage 4's workflow — it
  requires an explicit human confirmation step before anything is
  written.

## Logging restrictions

- **Provider logs cannot contain raw image bytes or embeddings.**
  Structured log calls anywhere in the face-recognition module log
  identifiers (`student_profile_id`, a request ID, a stable error code)
  and coarse outcomes (`MatchStatus`, `ProviderStatus`) — never a
  `pixel_data` value, an `EmbeddingVector.values` tuple, or any
  provider-internal exception string that might embed either. This
  extends the same rule `app.core.exceptions.unhandled_exception_handler`
  already applies project-wide (full detail server-side-logged only,
  generic message to the client) with a biometric-specific floor: even
  the server-side log must not carry the raw biometric payload itself.

## Model / provider diagnostics restrictions

- `app.modules.face_recognition.domain.ProviderHealth.detail` is
  intentionally short (`max_length=200`) and is meant for coarse status
  only (e.g. "model file not found") — never a full stack trace, a raw
  vendor HTTP response body, a file path that reveals server layout, or
  version/build fingerprinting detail beyond what a client legitimately
  needs. A length cap alone cannot fully guarantee this; enforcing the
  *content* restriction is a Stage 3+ code-review responsibility when a
  real `ProviderHealth` is constructed, not something Stage 1's type
  alone can prove.

## Students cannot enroll or inspect another student's biometric data

- Structurally enforced the same way `docs/adr/0008`'s ownership-check
  layer already enforces "a student can only read their own profile" —
  by deriving the acting student's identity from their authenticated
  session (`current_user.id`) and comparing it against the record's
  owning `student_profile_id`, concealing any mismatch as the resource's
  normal `404` rather than a distinguishable `403` (the same
  concealment convention `app.modules.auth.authorization` already
  establishes project-wide).

## Relationship to Phase 4's audit trail and attendance core

This policy assumes, and does not re-litigate, Phase 4's existing
guarantees: attendance writes are transactional
(`app.db.transaction`), authorization failures are independently
audited (`docs/adr/0010`), and role/ownership checks use the existing
concealment convention. Phase 5 adds biometric-specific rules on top of
those guarantees; it does not weaken or bypass any of them.

## Stage 2 implementation notes

Everything above this section is Stage 1 policy and is unchanged by
Stage 2. This section records how Stage 2 (`app/modules/biometric_enrollment/`)
implements it — see `docs/HANDOVER_PHASE_5_STAGE_2.md` for the full
design and rationale; this is a summary for anyone reading the policy
document itself.

### Authorization (confirms the Stage 1 decision above, does not change it)

- **Create, replace, request-deletion, finalize-deletion, and bulk-create
  are admin only.** There is no teacher role anywhere in this module —
  unlike attendance, a teacher's classroom assignment grants no scope
  over biometric enrollment. This is the concrete implementation of this
  policy's "students cannot enroll or inspect another student's
  biometric data" section above (an admin-only write surface makes that
  guarantee trivially true for the write side).
- **Reading one enrollment is admin, or the student themselves**,
  concealed exactly as this policy's "students cannot ... inspect
  another student's" section describes: a mismatch resolves to the same
  404 as a genuinely-missing enrollment, and the attempt is audited via
  the same `BlockedAuditWriter` Phase 4 already established.

### Storage layout

Under `Settings.BIOMETRIC_STORAGE_ROOT` (private, outside the web root,
validated at startup):

```
staging/       transient — not yet validated/committed (per-sample)
active/        the current, promoted sample for a student
quarantine/    marked for deletion; retryable purge target
bulk_staging/  a whole uploaded ZIP archive, before its members are
               individually extracted, validated, and staged above
```

Every file is addressed only by an opaque, server-generated key
(`uuid.uuid4().hex`) — never a client-supplied filename or path.
Promotion (`staging/` → `active/`) and quarantine (`active/` →
`quarantine/`) are atomic same-filesystem renames (`os.replace`).

### Lifecycle states

`BiometricEnrollment.status`: `pending` → `active` → `deletion_pending`
→ `deleted`.

`BiometricSample.status`: `pending` → `active` →
`replacement_pending`/`deletion_pending` → `quarantined` → `deleted`. At
most one `active` sample per enrollment, enforced by a partial unique
database index, not just service-layer logic.

`BiometricSample.processing_state` (`RecognitionProcessingState`):
`pending_processing` / `processed` / `processing_failed`. Stage 2 code
only ever wrote `pending_processing` — this was the concrete mechanism
behind this policy's (and the Stage 2 brief's) requirement that no
sample is ever claimed recognition-ready before Stage 3 successfully
embeds it. **Stage 3 resolution:** `processed`/`processing_failed` are
now written by `app.modules.face_recognition.processing_service`, as
originally planned — the enum itself needed no schema change (it was
declared at Stage 2 time exactly so it wouldn't). Stage 3 did add three
*new* nullable columns to this same table
(`processing_started_at`/`processing_completed_at`/
`processing_failure_reason_code`) via a new migration on top of
Stage 2's own (`d22bce264ecd`, parent `ca8e748dc8f2` — Stage 2's
migration file itself was not edited).

### Bulk ZIP manifest format

A root-level file named exactly `manifest.csv` (case-sensitive, no
directory prefix), UTF-8, with a header row containing at least
`student_profile_id` and `filename`. Each data row maps one archive
member (by its exact, case-sensitive in-archive path) to the student it
enrolls. Every member must be referenced by exactly one row, and every
row must reference exactly one present, valid member.

### Duplicate handling

- The same image content re-uploaded for the same student (while the
  earlier copy is not yet `deleted`) is rejected as a conflict — enforced
  by a database partial unique index on `(enrollment_id, sha256_hash)`
  scoped to non-deleted samples, not merely a service-layer check.
- Identical content across *different* students is explicitly allowed —
  the uniqueness above is scoped per enrollment, never global.
- Re-uploading previously-`deleted` content for the same student is
  allowed again (the partial index excludes `deleted` rows).

### Reconciliation

A read-only, admin-only report (`app/modules/biometric_enrollment/reconciliation.py`)
detects drift between the database and the filesystem — a row claiming
`active` with no corresponding file, an orphaned file with no row, a
sample stuck mid-transition past a configurable staging-timeout window.
It never repairs anything automatically, consistent with this
application having no background-worker architecture for a repair job
to run in; see that module's docstring for why any future automatic
repair must stay conservative and explicit rather than being added here.
