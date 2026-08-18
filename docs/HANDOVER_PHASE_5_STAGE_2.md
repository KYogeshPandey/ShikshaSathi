# Handover — Rebuild Phase 5, Stage 2 (Biometric Enrollment and Secure Photo Ingestion)

**Status: Stage 2 delivered, then corrected by a targeted, 8-item
correction patch applied in a follow-up session (see "Correction patch
applied after initial delivery" below for the full list), then corrected
a second time by a single-item, test-only patch (see "Second correction
patch (v3) — migration test upgrade/downgrade fix" below). Stage 3
(detection/embedding/matching) not started, in any of the three
sessions.** Built directly on the Phase 5 Stage 1 checkpoint
(`docs/HANDOVER_PHASE_5_STAGE_1.md`): Accepted ADR 0005, provider-neutral
`app.modules.face_recognition` contracts, the biometric `Settings` fields
Stage 1 introduced, and `docs/BIOMETRIC_DATA_POLICY.md`. No Stage 1
decision was reopened, reversed, or reinterpreted.

This document is the single source of truth for what Stage 2 actually is.
Read it before touching `app/modules/biometric_enrollment/` again — and
read the correction-patch sections below specifically before assuming any
narrative in the rest of this document (written before either patch) is
still 100% accurate regarding the eight-plus-one corrected behaviors;
each correction is called out inline at its original location too, but
the correction-patch sections are the authoritative summary.

---

## What this checkpoint actually is

A new, self-contained module — `app/modules/biometric_enrollment/` — that
accepts, validates, stores, replaces, and deletes a student's biometric
*photo sample*, safely and privately, with no face ever detected, aligned,
embedded, or matched anywhere in it. Concretely:

1. Two ORM tables (`BiometricEnrollment`, `BiometricSample`), one Alembic
   migration (`ca8e748dc8f2`, parent `e1208296dad5`), three native
   PostgreSQL enums, two database-enforced partial unique indexes.
2. A private, filesystem-backed storage abstraction with four zones
   (`staging/`, `active/`, `quarantine/`, `bulk_staging/`) under
   `Settings.BIOMETRIC_STORAGE_ROOT`, addressed only by server-generated
   opaque keys.
3. Pillow-based decoded-content image validation (format, dimensions,
   decompression-bomb guard, animated-frame rejection, MIME-mismatch
   check) — the one new runtime dependency this stage adds.
4. A single-enrollment lifecycle (create/replace/request-deletion/
   finalize-deletion) with documented, tested compensating cleanup for
   every point where a database write and a filesystem rename must both
   succeed.
5. A secure, manifest-driven bulk ZIP ingestion path
   (`zip_security.py`/`bulk_service.py`) that validates an entire archive
   — including the required `../../evil.jpg` path-traversal rejection —
   before a single byte is ever extracted, and is atomic with respect to
   validation (see "Bulk ZIP atomicity contract" below).
6. A read-only reconciliation report for database/filesystem drift.
7. Ten new test files (unexecuted in this sandbox — see "Checks not
   run").

---

## Read first, in order

1. `docs/BIOMETRIC_DATA_POLICY.md` — "Stage 2 implementation notes"
   section (appended this session, below the unchanged Stage 1 policy).
2. `app/modules/biometric_enrollment/models.py` — module docstring (the
   full schema-design rationale: why `storage_key` is separate from
   `id`, why the two partial unique indexes exist, why
   `RecognitionProcessingState` is its own column).
3. `app/modules/biometric_enrollment/service.py` — module docstring (the
   compensating-cleanup contract every create/replace/delete path
   follows).
4. `app/modules/biometric_enrollment/bulk_service.py` — module docstring
   (the exact atomicity contract, repeated below).
5. `app/modules/biometric_enrollment/zip_security.py` — module docstring
   (the manifest format, repeated below).
6. This document's "Known risks" section.

---

## Exact database design

### `biometric_enrollments`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | server-generated |
| `student_profile_id` | UUID, FK → `student_profiles.id` ON DELETE CASCADE | **unique** — at most one enrollment row per student |
| `status` | native enum `biometric_enrollment_status` | `pending` / `active` / `deletion_pending` / `deleted` |
| `created_by_user_id` | UUID, FK → `users.id` ON DELETE RESTRICT | the admin who created the enrollment |
| `deletion_requested_by_user_id` | UUID, FK → `users.id` ON DELETE SET NULL, nullable | who requested deletion |
| `deletion_requested_at` | timestamptz, nullable | |
| `created_at` / `updated_at` | timestamptz | server defaults |

### `biometric_samples`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | server-generated |
| `enrollment_id` | UUID, FK → `biometric_enrollments.id` ON DELETE CASCADE | |
| `storage_key` | `varchar(64)`, **unique** | opaque, server-generated (`uuid4().hex`) — **never** the row's own `id`; see models.py's docstring for why they are deliberately decoupled |
| `original_filename` | `varchar(255)`, nullable | sanitized metadata only, never used to build a path |
| `content_type` | `varchar(64)` | `image/jpeg` / `image/png` / `image/webp` |
| `file_size_bytes` | bigint | CHECK `> 0` |
| `width_px` / `height_px` | int | CHECK `> 0` each |
| `sha256_hash` | `varchar(64)` | CHECK `~ '^[0-9a-f]{64}$'` |
| `status` | native enum `biometric_sample_status` | `pending` / `active` / `replacement_pending` / `deletion_pending` / `quarantined` / `deleted` |
| `processing_state` | native enum `biometric_recognition_processing_state` | `pending_processing` / `processed` / `processing_failed` — **Stage 2 code only ever writes `pending_processing`** |
| `previous_sample_id` | UUID, FK → `biometric_samples.id` ON DELETE SET NULL, nullable | self-reference, set only on replace |
| `created_by_user_id` | UUID, FK → `users.id` ON DELETE RESTRICT | |
| `promoted_at` / `quarantined_at` / `deleted_at` | timestamptz, nullable | |
| `created_at` / `updated_at` | timestamptz | server defaults |

**Partial unique indexes (database-enforced, not just service-layer
assumptions):**

- `uq_biometric_samples_enrollment_active` — unique on `(enrollment_id)`
  WHERE `status = 'active'`. At most one active sample per enrollment.
- `uq_biometric_samples_enrollment_sha256_live` — unique on
  `(enrollment_id, sha256_hash)` WHERE `status != 'deleted'`. Rejects
  re-uploading identical content for the same student while the earlier
  copy is not yet deleted; explicitly does **not** apply across different
  students (allowed) or against `deleted` rows (re-enrollment with
  previously-deleted content is allowed).

---

## Migration

- **Revision:** `ca8e748dc8f2`
- **Parent:** `e1208296dad5` (Phase 4 head — immutable, not edited)
- **File:** `backend_v2/alembic/versions/20260804_1000_ca8e748dc8f2_create_biometric_enrollment_tables.py`
- Creates three native enums, then `biometric_enrollments`, then
  `biometric_samples` (child-after-parent), then all named indexes/
  constraints.
- `downgrade()` reverses in strict child-before-parent order:
  `biometric_samples` indexes → drop `biometric_samples` →
  `biometric_enrollments` indexes → drop `biometric_enrollments` → drop
  all three enum types (`checkfirst=True`, so no leftover type blocks a
  future re-creation).
- Not executed against a real database in this sandbox — see "Checks not
  run". Reviewed line-by-line against the Phase 4 migration
  (`e1208296dad5`)'s exact structure and naming convention.

---

## Storage layout

Under `Settings.BIOMETRIC_STORAGE_ROOT` (validated at startup, outside
the web root):

```
staging/<key>.tmp       transient, not yet validated/committed (per-sample)
active/<key>.bin        the current, promoted sample for a student
quarantine/<key>.bin    marked for deletion; retryable purge target
bulk_staging/<key>.zip  a whole uploaded ZIP archive, before extraction
```

`<key>` is always `uuid.uuid4().hex` (32 lowercase hex chars), generated
in `storage.py` — never accepted as a parameter from a router and never
derived from a client filename. Every path-building method validates the
key against that exact pattern and asserts the resolved path stays
inside the storage root (`BiometricStorageInvariantError` otherwise — an
internal-invariant guard, not a reachable attacker path, since no
external input ever becomes a `key`). Promotion (`staging/` → `active/`)
and quarantine (`active/` → `quarantine/`) are atomic same-filesystem
renames (`os.replace`).

---

## Lifecycle / state machine

**Enrollment:** `pending` (created, no sample yet) → `active` (has an
active sample) → `deletion_pending` → `deleted`.

**Sample:**

```
pending ──(promote)──> active ──(replace)──> replacement_pending
                          │                          │
                          └──(delete)──> deletion_pending
                                              │
                                              ▼
                                        quarantined ──(purge)──> deleted
```

Every transition that pairs a database write with a filesystem operation
follows the same order, documented in `service.py`'s module docstring:
stage → validate → persist a `PENDING` row (its own commit) → attempt the
filesystem rename → only then transition the row to its next status (a
separate commit). If the rename fails, the orphaned `PENDING` row is
deleted (compensating cleanup) before the original `OSError` is
re-raised — the student is never left with a falsely active enrollment.
If that compensating delete itself fails, the row is left `PENDING` with
no backing file — exactly the drift shape `reconciliation.py` is built to
detect and report (never auto-repaired).

`replace_sample`'s specific ordering (see `service.py`): the *old*
sample's status is flipped off `active` in the **same transaction**, and
**before**, the new sample is marked `active` — this exists precisely to
never transiently violate the "one active sample per enrollment" partial
unique index within that transaction. The old sample's actual file
retirement (quarantine → purge) happens **after** that transaction
commits, as a best-effort step: a failure there is logged and left as
reconciliation-visible drift (a lingering `replacement_pending` sample),
not surfaced as an error on the replace call — the replace call's real
guarantee (the student has a new active sample) is already durable by
that point.

Deletion (`request_deletion` / `finalize_deletion`) is one resumable
state-machine method (`_advance_deletion`) called by both endpoints: it
inspects the sample's *current* status and advances exactly one step,
re-checking after each mutation, so a single call cascades through every
remaining stage in the common case, and a retry after a crash resumes
from wherever the previous attempt actually got to. Calling either
endpoint on an already-`deleted` enrollment is a safe no-op.

---

## Authorization

Confirmed and implemented exactly per `docs/BIOMETRIC_DATA_POLICY.md`
Stage 1 (Accepted) — **not reopened this session**:

- **Create / replace / request-deletion / finalize-deletion / bulk-create:
  admin only.** No teacher role anywhere in this module — an admin's role
  already grants full scope over every student, so (unlike attendance)
  there is no object-level ownership-check dependency needed here.
- **Read one enrollment: admin, or the student themselves.** A student
  requesting another student's enrollment gets the same concealed `404`
  a genuinely-missing enrollment would (`app.modules.profiles
  .student_router`'s established pattern), and the attempt is
  independently audited via `app.modules.attendance.service
  .BlockedAuditWriter` — reused as-is, not reimplemented.
- **Inactive students are rejected** for create/replace (an admin cannot
  enroll biometric data for a deactivated student profile) and for
  self-service read (mirrors `StudentProfileService.get_for_user`'s
  existing admin-exempt `is_active` check).

---

## Bulk ZIP manifest format

A root-level file named exactly `manifest.csv` (case-sensitive, no
directory prefix), UTF-8, header row with at least `student_profile_id`
and `filename`. Each data row maps one archive member (its exact,
case-sensitive in-archive path) to the student it enrolls. Every
non-manifest member must be referenced by exactly one row; every row must
reference exactly one present, valid member. Duplicate rows (same
student twice, or same filename twice) are rejected.

## ZIP security controls (pre-extraction, `zip_security.py`)

Rejected before any member is ever read, each with its own error code
(`details.errors[].code` in the `422` response): `../` and backslash
traversal, absolute paths, drive-letter paths, symlink entries, encrypted
entries, nested-archive extensions, unsupported extensions, empty
members, per-file/total uncompressed-size caps, suspicious compression
ratios, duplicate normalized paths, a missing/malformed manifest, a
manifest row referencing an absent file, and an archive member not
referenced by any row. **`ZipFile.extractall()`/`.extract()` are never
called anywhere in this application.** The one safe read path
(`stream_member_to_path`) enforces its byte cap against bytes actually
produced by the decompressor — not against the archive's own
(spoofable) size metadata.

## Bulk ZIP atomicity contract

1. **Validation phase** (`zip_security.validate_archive` +
   `bulk_service._prepare_rows`): every row is fully checked — archive
   shape/security, per-image decode/format/dimension, student
   existence/active/enrollment-state, per-enrollment duplicate-content —
   with **zero** side effects. Every problem found is collected, not just
   the first.
2. **Gate:** if *any* row failed either part of validation, the entire
   batch is rejected: every staged file is discarded, **zero** database
   rows are created. An archive-level problem (bad ZIP, unsafe path,
   missing manifest, etc.) never even produces a `BulkEnrollmentResult` —
   it surfaces as a plain `422`/`413` error response before row
   processing starts. A row-level problem (student not found/inactive/
   already enrolled, duplicate content) produces `BulkEnrollmentResult
   (success=False, enrolled_count=0, rows=[...])`, every row reported
   failed (the individually-valid rows carry `ROW_BATCH_REJECTED`).
3. **Execution phase**, reached only when every row passed validation:
   each row is processed through the same staged→PENDING→promote→ACTIVE
   sequence single enrollment uses. The one scenario this cannot be
   perfectly all-or-nothing for is a genuine infrastructure failure
   (disk, database) partway through this phase, after every row already
   passed validation — see "Known risks".

---

## Duplicate handling (summary — full detail in `docs/BIOMETRIC_DATA_POLICY.md`)

| Scenario | Behavior |
|---|---|
| Same content, same student, old copy not deleted | Rejected (`ENROLLMENT_DUPLICATE_CONTENT` / `ROW_DUPLICATE_CONTENT`) |
| Same content, different students | Allowed |
| Same content, same student, old copy already `deleted` | Allowed (re-enrollment) |
| Duplicate filename, different bytes | Allowed (filename is metadata only) |
| Duplicate manifest row (student or filename) | Rejected at archive-validation time |
| Create while enrollment `deletion_pending` | Rejected (`ENROLLMENT_DELETION_PENDING`) |

---

## Reconciliation

`reconciliation.py`'s `ReconciliationService.generate_report()` (exposed
as `GET /api/v1/biometric-enrollments/reconciliation/report`, admin-only)
detects, **without ever repairing**: an `active` row with no active-zone
file; an active-zone file with no `active` row (excluding
`replacement_pending`/`deletion_pending` samples, which legitimately still
have a file there mid-transition); the same two checks for the
quarantine zone; a staged file with no `pending` row; a `pending` row
older than `Settings.ENROLLMENT_STAGING_TIMEOUT_MINUTES` (default 60);
and every `replacement_pending` sample, unconditionally (Stage 2 has no
automatic follow-up for a stalled replacement retirement — see "Known
risks"). No automatic repair exists; this application has no
background-worker architecture for one to run in, and the module
docstring says explicitly that any future automatic repair must be
conservative, explicit, and tested — not added speculatively here.

---

## Dependencies added and why

- **`pillow>=10.4,<13.0`** (`backend_v2/pyproject.toml`) — decoded-content
  image validation only (format sniffing, dimension/pixel checks,
  decompression-bomb guard, animated-frame detection). Never used for
  face detection.

**Explicitly not added** (per the Stage 2 brief and this module's own
design): `opencv-python-headless`, `onnxruntime`, `numpy` for inference,
TensorFlow, PyTorch, MTCNN, InsightFace, DeepFace, or any hosted
face-recognition API SDK.

---

## Exact files created

```
backend_v2/alembic/versions/20260804_1000_ca8e748dc8f2_create_biometric_enrollment_tables.py

backend_v2/app/modules/biometric_enrollment/__init__.py
backend_v2/app/modules/biometric_enrollment/models.py
backend_v2/app/modules/biometric_enrollment/errors.py
backend_v2/app/modules/biometric_enrollment/storage.py
backend_v2/app/modules/biometric_enrollment/image_validation.py
backend_v2/app/modules/biometric_enrollment/repository.py
backend_v2/app/modules/biometric_enrollment/schemas.py
backend_v2/app/modules/biometric_enrollment/service.py
backend_v2/app/modules/biometric_enrollment/zip_security.py
backend_v2/app/modules/biometric_enrollment/bulk_service.py
backend_v2/app/modules/biometric_enrollment/router.py
backend_v2/app/modules/biometric_enrollment/reconciliation.py

backend_v2/app/tests/phase5_stage2_http_helpers.py
backend_v2/app/tests/test_phase5_stage2_model_registration.py
backend_v2/app/tests/test_migrations_phase5_stage2.py
backend_v2/app/tests/test_phase5_stage2_storage.py
backend_v2/app/tests/test_phase5_stage2_image_validation.py
backend_v2/app/tests/test_phase5_stage2_zip_security.py
backend_v2/app/tests/test_phase5_stage2_enrollment_http.py
backend_v2/app/tests/test_phase5_stage2_bulk_zip_http.py
backend_v2/app/tests/test_phase5_stage2_failure_injection.py
backend_v2/app/tests/test_phase5_stage2_reconciliation.py

docs/HANDOVER_PHASE_5_STAGE_2.md
```

This list was produced by diffing the working tree against a fresh
extraction of the original Stage 1 baseline ZIP (`diff -rq`), not
reconstructed from memory.

## Exact files modified

```
.env.example                          (root)
backend_v2/.env.example
backend_v2/README.md
backend_v2/pyproject.toml
backend_v2/alembic/env.py
backend_v2/app/api/router.py
backend_v2/app/core/config.py
backend_v2/app/db/models.py
backend_v2/app/tests/conftest.py
docs/ARCHITECTURE.md
docs/BIOMETRIC_DATA_POLICY.md
docs/IMPLEMENTATION_PLAN.md
docs/PROGRESS.md
```

Confirmed **not modified**: every Phase 1-4 migration file, `app/modules/
face_recognition/` (byte-for-byte unchanged from Stage 1), every Phase
1-4 API contract, all legacy `backend/`/`frontend/` code.

### Correction patch (follow-up session) — exact files modified

```
backend_v2/app/modules/biometric_enrollment/models.py
backend_v2/app/modules/biometric_enrollment/service.py
backend_v2/app/modules/biometric_enrollment/repository.py
backend_v2/app/modules/biometric_enrollment/bulk_service.py
backend_v2/app/modules/biometric_enrollment/zip_security.py

backend_v2/app/tests/test_phase5_stage2_image_validation.py
backend_v2/app/tests/test_phase5_stage2_failure_injection.py
backend_v2/app/tests/test_phase5_stage2_bulk_zip_http.py
backend_v2/app/tests/test_phase5_stage2_zip_security.py
backend_v2/app/tests/test_migrations_phase5_stage2.py

docs/HANDOVER_PHASE_5_STAGE_2.md
docs/PROGRESS.md
```

No file outside this list was touched by the correction patch. No file
under `app/modules/face_recognition/`, no migration file, and no router/
schema file was touched — every fix was a bug fix inside an existing
service/repository/security-validation function, a test correction, or a
documentation correction. See "Correction patch applied after initial
delivery" above for exactly what changed in each file and why.

### Second correction patch (v3) — exact files modified

```
backend_v2/app/tests/test_migrations_phase5_stage2.py

docs/HANDOVER_PHASE_5_STAGE_2.md
docs/PROGRESS.md
```

No file outside this list was touched by the v3 patch. No application
code, migration file, model, router, schema file, or unrelated test was
touched — the single change is a one-line fix inside an existing test
function plus the matching documentation update. See "Second correction
patch (v3) — migration test upgrade/downgrade fix" below for exactly
what changed and why.

---

## Tests — exact list and what each covers

| File | Needs DB | Covers |
|---|---|---|
| `test_phase5_stage2_model_registration.py` | No | Table/enum registration, constraint/index presence |
| `test_migrations_phase5_stage2.py` | Yes (self-skips) | Upgrade/downgrade round-trip, enum values, table presence at each state. **(correction patch)** Rewritten to never assume `"head" == ca8e748dc8f2`: upgrades to true latest head first, downgrades explicitly to `ca8e748dc8f2` for every Stage-2 assertion, downgrades further to Phase 4 head, re-upgrades specifically to `ca8e748dc8f2`, and restores true latest head in `finally` — stays valid unmodified once Stage 3 adds a migration on top. **(v3 correction)** the first move to `ca8e748dc8f2` is a `command.downgrade` (was incorrectly coded as `command.upgrade` in the v2 patch, which only happened to work while Stage 2 was still the true head). |
| `test_phase5_stage2_storage.py` | No | Staging cap enforcement + cleanup, promote/quarantine/purge lifecycle, key-format invariant, per-zone key listing |
| `test_phase5_stage2_image_validation.py` | No | Valid JPEG/PNG, empty/truncated/non-image rejection, unsupported format, animated rejection, dimension/pixel caps, MIME-mismatch |
| `test_phase5_stage2_zip_security.py` | No | Valid manifest; **`../../evil.jpg` traversal rejection (required regression)**; backslash/absolute/drive paths; symlink; encrypted member; nested archive; unsupported extension; duplicate path; excessive count/size; missing/invalid manifest; missing-file/unreferenced-member/duplicate-row manifest errors; multi-problem reporting; bounded member streaming + cap enforcement; **(correction patch)** duplicate-student detection catches a canonical-vs-uppercase/braced UUID representing the same student |
| `test_phase5_stage2_enrollment_http.py` | Yes | 401/403 role gating; successful create with safe-metadata-only response; already-active conflict; inactive-student conflict; corrupt-image 422; oversized-upload 413 (settings monkeypatch); replace success + old-sample retirement; replace-with-no-active conflict; same-student duplicate-content conflict; cross-student duplicate allowed; admin/self read; blocked-read concealment + audit; teacher-read 403; success-audit assertion; delete-without-enrollment 404; full delete lifecycle + idempotent finalize; re-enrollment after full deletion |
| `test_phase5_stage2_bulk_zip_http.py` | Yes | 401/403; valid multi-row batch; **`../../evil.jpg` at the HTTP layer (required regression)**, zero writes; missing manifest; unreferenced member; duplicate manifest row; unknown-student row (atomic rejection, zero writes); already-active-student row (atomic rejection); success audit log; **(correction patch)** oversized ZIP returns `BULK_ENROLLMENT_ZIP_TOO_LARGE` (not the single-image error code); an archive-level rejection (path traversal) writes a `BLOCKED` bulk-attempt audit record with exactly the two safe aggregate counts, before the original error is re-raised |
| `test_phase5_stage2_failure_injection.py` | Yes | Promote-failure compensating cleanup on create (no falsely-active sample); retry-after-fix; promote-failure on replace (old sample undisturbed); best-effort retirement failure does not fail the replace call; deletion state-machine resumes correctly after a quarantine failure; **(correction patch)** deletion drains a stalled `replacement_pending` artifact left by a prior failed retirement, not only the current active sample; DB/audit-write failure *after* filesystem promote is compensated on create, replace, and bulk execution (orphaned file quarantined+purged, orphaned row removed, no falsely-active enrollment); every failed bulk-execution row has its staged file discarded |
| `test_phase5_stage2_reconciliation.py` | Yes | Admin-only gating; orphaned active/staged/quarantined file findings; stale-`pending`-sample finding; `replacement_pending` finding; read-only (nothing deleted/modified by generating a report) |

**Total: 10 new test files.** None executed in this sandbox — see next
section.

---

## Verification commands actually run and exact results

- `python -m compileall -q app alembic` (from `backend_v2/`) — **passed**,
  0 errors, across every new/modified file, run repeatedly through the
  session as files were edited.
- A custom AST-based unused-import scan across every new/modified `.py`
  file — **0 findings** (two genuinely-unused imports caught and removed
  during the session: `BiometricSampleDeletionResult` in `service.py`,
  `UserRepository` in `bulk_service.py`).
- A CRLF-safe line-length scan (strips a trailing `\r` before measuring,
  so it is accurate against this repository's pre-existing mixed line
  endings) against the configured Ruff `line-length = 100` — **0 lines
  over 100 characters** across every new/modified file, after fixing all
  violations found during the session.
- Trailing-whitespace scan — **0 matches**.
- Broad-exception scan (`except Exception`/bare `except:`) across
  `app/modules/biometric_enrollment/` — **6 matches**, each reviewed
  individually and given an inline comment explaining why the catch is
  broad there specifically (compensating cleanup that must run
  regardless of the failure's exact type, or a best-effort secondary
  operation that must never mask the primary result/error — see "Ruff
  configuration and the `except Exception` review" below for the full
  accounting). Two additional sites that could be narrowed safely
  (`validate_image_file`'s own documented contract of never raising
  anything but an `AppError`) were narrowed to `except AppError`.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan across the new
  module and its tests — **0 matches** as executable code (the only
  `NotImplementedError`-adjacent text is inside docstrings describing
  what Stage 3 will implement).
- Secret/hardcoded-credential/debug-print scan across the new module —
  **0 matches**.
- Cache/`__pycache__`/`.pyc`/real-`.env`/model-file scan across the
  session's changes — **0 matches**.
- Stage-3-scope scan: confirmed no detection/embedding/matching code
  exists anywhere in the new module, and `app/modules/face_recognition/`
  is byte-for-byte unchanged from the Stage 1 checkpoint (diffed against
  a fresh extraction of the Stage 1 baseline ZIP).
- Two **standalone, real-production-source** verification runs (not mere
  static review) — the two most safety-critical modules were executed
  directly, not just read:
  - `zip_security.py`'s actual functions (`validate_archive`,
    `stream_member_to_path`), dependency-injected against lightweight
    stand-ins for `app.core.config.Settings` and the two `AppError`
    subclasses it imports (neither `pydantic` nor `fastapi` is installed
    in this sandbox), run against real ZIP archives built with the
    standard-library `zipfile` module: the required `../../evil.jpg`
    traversal (confirmed rejected, confirmed nothing extracted), a
    symlink entry, an encrypted entry (the entry's flag bits had to be
    binary-patched into the archive's raw local/central-directory bytes
    after writing, since `zipfile.ZipFile.writestr` does not preserve a
    manually-set `ZipInfo.flag_bits`), backslash/absolute/drive-letter
    paths, a nested-archive extension, an unsupported extension, a
    missing manifest, an unreferenced member, a duplicate-student
    manifest row, a duplicate-filename manifest row, an invalid
    student-ID format, and a suspicious compression ratio (a 2 MB
    all-zero payload). Every scenario produced exactly the error code
    the corresponding pytest test expects.
  - `storage.py`'s actual functions, similarly dependency-injected (a
    minimal `Settings` stand-in and a no-op logger, since `structlog`
    is also not installed in this sandbox), confirmed: zone-directory
    creation, key generation, the full stage→promote→quarantine→purge
    lifecycle with correct file movement at each step, byte-cap
    enforcement during staged writes with cleanup on overflow, and the
    internal key-format invariant rejecting a would-be traversal key.
- A standalone Pillow smoke test (separate from the pytest file, using
  the real, installed Pillow 12.1.1) confirmed the exact API behavior
  `image_validation.py` relies on: `Image.DecompressionBombError`/
  `Image.DecompressionBombWarning` under a tightened `MAX_IMAGE_PIXELS`,
  and `is_animated`/`n_frames` detection for an animated WEBP (only once
  `duration`/`loop` are set on save — Pillow does not treat every
  multi-frame save call as "animated" without them, which is why the
  actual pytest fixture (`_write_animated_webp`) explicitly sets both).

### Ruff configuration and the `except Exception` review

`backend_v2/pyproject.toml`'s `[tool.ruff.lint]` selects
`["E", "F", "I", "UP", "B", "C4", "SIM", "RUF"]` — **`BLE001`
(flake8-blind-except) is not enabled**, and `app.modules.attendance
.service`'s own established `except Exception as exc:` sites carry no
`noqa` comment. An earlier pass in this session had added
`# noqa: BLE001 - <reason>` comments to every broad-except site in the
new module; these were removed as decorative (they suppress a rule that
was never active) and replaced with plain, self-contained prose comments
explaining the rationale at each site — matching the existing codebase's
convention exactly, not inventing a new one.

### Correction-patch session — verification commands actually run

Working from the delivered `ShikshaSathi-phase-5-stage-2.zip` as the sole
baseline. Same sandbox (no network egress, no installed project
dependencies) as the original session above — see "Checks not run"
below for what that means here specifically.

- `python3 -m compileall -q app alembic` (from `backend_v2/`) —
  **passed**, 0 errors, run against the entire tree (not only the files
  touched this session), both mid-session after each edit and again as
  a final sweep before packaging.
- A symtable-based free-variable scan (a `NameError`-candidate check —
  every function's free variables checked against module-level names and
  builtins) across all ten files touched this session — **0 genuine
  findings**. The scan flagged six closures as "possible issues": two are
  pre-existing, untouched code in `zip_security.py` (lines 199-207 and
  394/424 — unrelated to this session's edit, which only touched
  `_parse_manifest`'s duplicate-detection block), and four are this
  session's own new monkeypatch/spy helper closures in
  `test_phase5_stage2_failure_injection.py` and
  `test_phase5_stage2_bulk_zip_http.py`. All six are ordinary Python
  closures over an *enclosing function's* locals (e.g. a `_spy` inner
  function reading `captured`/`original_promote` from its enclosing
  factory function) — a case this module-scope-only scan cannot resolve.
  Each was checked by hand against the source and confirmed correct; none
  is a real undefined-name defect.
- CRLF-safe line-length scan (Ruff's configured `line-length = 100`)
  across all ten files touched this session — **0 lines over 100
  characters**.
- Trailing-whitespace and hard-tab scan across all ten files — **0
  matches**.
- Bare `except:` scan across all ten files — **0 matches**.
- TODO/FIXME/XXX scan across all ten files — **0 matches**.
- Hardcoded-secret/credential pattern scan across all ten files — **0
  genuine matches** (`_VALID_SECRET = "a" * 40` in two test files'
  pre-existing fixture setup, present before this session, is a
  synthetic placeholder flagged only by the pattern's breadth, not a
  real credential).
- Duplicate function/class-definition scan (exact qualified name, across
  every file touched this session) — **0 duplicates** in the delivered
  result. (One was introduced and caught mid-session: an early edit to
  `test_migrations_phase5_stage2.py` left the pre-existing function body
  duplicated as dead code after the rewritten one; a `view` immediately
  after the edit caught it and it was removed before any check ran or
  any file was packaged.)
- Manual Stage-3-scope re-scan: confirmed no detection/embedding/
  matching/recognition-attendance/OpenCV/ONNX/model-file code exists
  anywhere in this session's changes, and that
  `app/modules/face_recognition/` remains byte-for-byte unchanged from
  the Stage 1 checkpoint (unmodified by this session — it was never
  opened).
- Migration/model/router/scope scan: confirmed no Alembic migration file,
  no router file (`router.py`), and no Pydantic schema file
  (`schemas.py`) was touched by any of the eight corrections — every fix
  is contained inside `models.py` (constraint names only — column/table
  definitions unchanged), `service.py`, `repository.py`,
  `bulk_service.py`, `zip_security.py`, or a test file.
- Cache/`__pycache__`/`.pyc`/real-`.env`/model-file scan across the
  working tree — any interpreter-generated cache directories created by
  this session's own `compileall`/`py_compile` runs were removed before
  packaging (see the delivered ZIP's manifest below); no real `.env`
  file or model/weights file exists anywhere in the tree.
- `pip install ruff` / `pip install mypy` / `pip install pytest` — each
  attempted and each failed identically to the original session: no
  network egress in this sandbox (`ERROR: Could not find a version that
  satisfies the requirement ... No matching distribution found`).

### Second correction patch (v3) — verification commands actually run

Working from `ShikshaSathi-phase-5-stage-2-v2.zip` as the sole baseline
for this pass. Same sandbox constraints as both prior sessions.

- `python3 -m compileall -q app` (from `backend_v2/`) — **passed**, 0
  errors, run against the entire tree after the edit.
- The full `test_migrations_phase5_stage2.py` file was re-read end-to-end
  to confirm: the change is the single intended line (the first move to
  `PHASE5_STAGE2_HEAD_REVISION`, immediately after `command.upgrade(cfg,
  "head")`, now reads `command.downgrade`); the later re-upgrade to
  `PHASE5_STAGE2_HEAD_REVISION` (after the explicit downgrade to the
  Phase 4 head) was correctly left as `command.upgrade`, since that move
  is genuinely forward; and the single `try`/`finally` structure and the
  `finally` block's own `command.upgrade(cfg, "head")` are both
  unchanged.
- Duplicate function/class-definition scan and CRLF-safe line-length scan
  re-run against the one changed file — **0 findings**, **0 lines over
  100 characters**.
- Migration/model/router/scope scan re-run: confirmed no file other than
  the one test file and the two documentation files listed above was
  touched.
- Stage-3-scope re-scan: confirmed no detection/embedding/matching code
  exists anywhere, unchanged from both prior sessions.
- `pip install pytest` — attempted, failed identically to both prior
  sessions (no network egress).

---

## Checks not run, and precisely why

Identical sandbox limitation to every prior phase's session, confirmed
again this session: `pip install <anything>` is blocked (no network
egress), and `fastapi`/`pydantic`/`pydantic-settings`/`sqlalchemy`/
`pytest`/`ruff`/`mypy` are all confirmed not installed. Only `Pillow`
(already present) could be exercised directly.

- **`pytest`** — no collection or run of any kind, targeted or full
  suite. All ten new test files are `py_compile`-clean and reviewed
  against already-established fixture conventions, but have never been
  executed by a real test runner.
- **`ruff format --check` / `ruff check`** — unavailable. The CRLF-safe
  line-length scan and the AST-based unused-import scan above are the
  closest static substitutes actually run, and are not a substitute for
  the full rule set (`E, F, I, UP, B, C4, SIM, RUF`) a real Ruff pass
  would check (import sort order was reviewed manually; simplification
  opportunities under `SIM` were not exhaustively checked).
- **`mypy app`** — unavailable. Every new function has an explicit
  return-type annotation and every new class attribute is typed, but no
  type-checker has actually run against this code.
- **`alembic upgrade head` / `downgrade`** — unavailable (no reachable
  PostgreSQL instance in this sandbox). The migration was reviewed
  line-by-line against Phase 4's migration structure/style instead, and
  `test_migrations_phase5_stage2.py` is written to self-skip (not fail)
  when no database is reachable, matching `test_migrations_phase4.py`'s
  established pattern.
- **`docker compose ...`** — unavailable, Docker itself is not present.

No check above is claimed to have passed where it was not actually run.
Where full execution was impossible, the closest available static or
standalone-source verification was performed instead (see the previous
section) and is never presented as equivalent to the runtime check it
stands in for. The repository owner should run the full Docker/pytest/
Ruff/mypy gate — starting with `alembic upgrade head` against a real
PostgreSQL instance — before trusting this checkpoint's runtime behavior.
See `backend_v2/README.md`'s new "Phase 5 Stage 2 database-backed tests"
section for the exact commands.

### Correction-patch session — checks unavailable, and precisely why

Same as the original session, restated because a reader may land on this
correction-patch section directly: `fastapi`/`pydantic`/
`pydantic-settings`/`sqlalchemy`/`pytest`/`ruff`/`mypy` are all confirmed
not installed, and `pip install` of any of them is confirmed blocked (no
network egress). As a direct, honest consequence for this correction
patch specifically:

- **`pytest`** — no collection or run, targeted or full. All five newly
  added test functions (`test_finalize_deletion_drains_stalled_replacement_artifact_too`,
  `test_create_sample_activation_failure_after_promote_leaves_no_falsely_active_sample`,
  `test_create_sample_activation_failure_allows_retry_after_fix`,
  `test_replace_sample_activation_failure_preserves_old_active_sample`,
  `test_bulk_activation_failure_after_promote_compensates_and_reports_row_failed`,
  `test_bulk_execution_failure_discards_staged_file_for_every_failed_row`,
  `test_duplicate_student_row_different_uuid_representation_is_rejected`,
  `test_bulk_oversized_zip_returns_413_with_correct_error_code`,
  `test_bulk_archive_level_rejection_writes_blocked_audit`) plus the two
  rewritten tests (constraint-name assertions in
  `test_phase5_stage2_model_registration.py` — unchanged, but now
  expected to pass instead of fail against the fixed `models.py`; the
  rewritten `test_phase5_stage2_migration_round_trip`) are `py_compile`-
  clean and were checked by hand, statement-by-statement, against the
  exact production code paths they exercise, but none has ever been
  executed by a real test runner.
- **`ruff format --check` / `ruff check`** — unavailable. The CRLF-safe
  line-length scan and the symtable-based free-variable scan above are
  the closest static substitutes actually run this session, and are not
  a substitute for Ruff's full configured rule set.
- **`mypy app`** — unavailable. Every new/changed function signature
  keeps its existing type annotations; no type-checker has run against
  this session's changes.
- **`alembic upgrade head` / `downgrade`** — unavailable (no reachable
  PostgreSQL instance). The rewritten
  `test_phase5_stage2_migration_round_trip` was re-read end-to-end after
  fixing a self-introduced dead-code duplication (caught and removed
  before packaging — see the correction-patch section above) to confirm
  it is a single, correctly structured function with one `try`/`finally`
  and the exact `command.upgrade`/`command.downgrade` sequence item 8
  requires — but it has not actually been run against a database this
  session, same as the original delivery.
- **`docker compose ...`** — unavailable, Docker itself is not present.

No check above is claimed to have passed where it was not actually run.
The repository owner should run the full Docker/pytest/Ruff/mypy gate —
starting with `alembic upgrade head` against a real PostgreSQL instance —
against `ShikshaSathi-phase-5-stage-2-v2.zip` before trusting either this
correction patch's or the original delivery's runtime behavior.

### Second correction patch (v3) — checks unavailable, and precisely why

Identical sandbox limitation, restated for a reader landing here
directly: `pytest`/`alembic`/`sqlalchemy`/`asyncpg` are not installed and
no PostgreSQL instance is reachable.

- **`pytest`** — no collection or run. The one-line change was verified
  by re-reading the full function against both the delivered `docstring`
  update and the unchanged later re-upgrade call, not by executing it.
- **`alembic upgrade head` / `downgrade`** — unavailable. The corrected
  `command.downgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)` call was checked
  against the same revision constants (`PHASE5_STAGE2_HEAD_REVISION =
  "ca8e748dc8f2"`, `PHASE4_HEAD_REVISION = "e1208296dad5"`) already used
  and verified-by-hand in the v2 correction — it was not run against a
  database this session.

No check above is claimed to have passed where it was not actually run.
The repository owner should run the full pytest/alembic gate against
`ShikshaSathi-phase-5-stage-2-v3.zip` before trusting this test's runtime
behavior, same recommendation as both prior sessions.

---

## Known risks

1. **Bulk ZIP execution-phase infrastructure failure is not perfectly
   atomic.** If every row in a batch passes pre-validation and a genuine
   infrastructure failure (disk full, database connection lost) occurs
   partway through the execution phase, rows already processed before
   the failure remain enrolled — the batch reports `success=False` with
   `enrolled_count > 0` (the one documented exception to "success=False
   implies enrolled_count == 0", called out explicitly in
   `BulkEnrollmentResult`'s own docstring). A true multi-row 2-phase-
   commit is out of scope for Stage 2.
2. **`replacement_pending` retirement has no automatic follow-up before a
   deletion is requested.** If a replace call's best-effort old-sample
   retirement (quarantine → purge) fails and is never retried, the old
   sample stays `replacement_pending` indefinitely with its file still on
   disk. `reconciliation.py` reports every such sample unconditionally,
   but nothing acts on the finding automatically *while the enrollment
   stays active* — this is a real, not-yet-closed gap for a future stage
   (or a scheduled job, once one exists) to pick up. **Narrowed by the
   correction patch's item 3, but not eliminated:** a subsequent
   enrollment *deletion* now correctly drains a stalled
   `replacement_pending` sample too (see "Correction patch applied after
   initial delivery" above), so the drift no longer survives forever if
   the student is ever deleted — but an enrollment that stays active
   indefinitely with a stalled `replacement_pending` sample sitting
   behind it still has no automatic retry path outside of an explicit
   deletion.
3. **No test in this sandbox has actually executed against PostgreSQL.**
   Every HTTP/DB-backed test is written against established, already-
   passing Phase 1-4 fixture conventions and reviewed carefully, but a
   genuine schema mismatch, transaction-ordering bug, or async-session
   issue could still exist and would only surface under a real `pytest`
   run against real PostgreSQL.
4. **`declared_content_type` mismatch policy is strict but simple.**
   `image_validation.py` only compares the header against a small
   recognized set (`image/jpeg`, `image/jpg`, `image/png`, `image/webp`)
   and ignores anything else (including a blank header) — a client that
   sends a wrong-but-unrecognized Content-Type will not be caught by this
   check (though the underlying Pillow format-sniffing still governs
   what is actually stored).
5. **`BIOMETRIC_STORAGE_ROOT`'s default (`var/biometric_data`, relative
   to the process's working directory) is unchanged from Stage 1** and
   is not itself made absolute or otherwise hardened in Stage 2 — a
   production deployment must still set it explicitly to an absolute,
   private path outside any web root, per `docs/BIOMETRIC_DATA_POLICY.md`.

---

## Deferred inference dependencies (unchanged from Stage 1, restated for clarity)

`opencv-python-headless` and `onnxruntime` are still not added anywhere
in this repository. Stage 2 needed neither (Pillow alone covers decode/
format/dimension validation) and does not change Stage 1's assessment of
when either becomes necessary.

---

## Correction patch applied after initial delivery

A dedicated review pass (separate follow-up session, working from the
delivered Stage 2 ZIP as the authoritative baseline — no re-inspection of
already-correct code, no Stage 3 work) found and fixed eight defects. All
eight are fixed in the code now in this repository; this section is the
permanent record of what was wrong and exactly what changed. No API
contract, response schema, database schema, or authorization decision
changed — every fix is either a bug fix inside an existing code path, a
test correction, or a documentation correction.

1. **ORM `CheckConstraint` names were silently double-prefixed.**
   `models.py` passed already-prefixed names (e.g.
   `name="ck_biometric_samples_width_px_positive"`) to `CheckConstraint`.
   Because `app/db/naming.py`'s naming convention is
   `"ck_%(table_name)s_%(constraint_name)s"`, and a `CheckConstraint`'s
   `name=` argument *is* the `%(constraint_name)s` token's source value
   (a `CheckConstraint` has no participating columns to derive a name
   from the way a `UniqueConstraint`/`ForeignKeyConstraint` can), the
   *actual* resolved constraint name SQLAlchemy produced was
   `ck_biometric_samples_ck_biometric_samples_width_px_positive` —
   doubled, and not matching either the Alembic migration's literal names
   or `test_phase5_stage2_model_registration.py`'s own assertions (which
   were already correct and would have caught this under a real test
   run). Fixed by passing bare names (`name="width_px_positive"`, etc.)
   for all four check constraints.
2. **The pixel-cap test used an invalid configured value.**
   `test_pixel_count_over_configured_max_is_rejected_even_within_per_side_limit`
   constructed `Settings(MAX_ENROLLMENT_IMAGE_PIXELS=100_000, ...)` —
   below `Settings`'s own field validator's minimum of `1_000_000` (see
   `app/core/config.py`), so the test would fail at `Settings`
   construction with a `pydantic.ValidationError` before ever reaching
   the image-validation logic under test. Fixed to use the lowest *legal*
   cap, `1_000_000`, with a `1100x1000` (1,100,000px) fixture image —
   over the cap, but with each individual side still well under the
   separate per-dimension cap, so the test still exercises the intended
   "pixel count over cap, even though both sides are individually fine"
   guard.
3. **Deletion only ever drained a single sample, not every live one.**
   `BiometricEnrollmentService._advance_deletion` looked for at most one
   sample (the current `ACTIVE` one, or one found by a narrow
   `DELETION_PENDING`/`QUARANTINED` scan) and then unconditionally marked
   the enrollment `DELETED` regardless of whether other live samples
   existed. Concretely: if a prior `replace_sample` call's best-effort
   old-sample retirement had stalled (see "Known risks" #2 below — this
   was already a known, accepted gap on its own), the old sample sits at
   `REPLACEMENT_PENDING` with its file still on disk. A subsequent
   enrollment deletion would drain only the new `ACTIVE` sample, then
   immediately mark the enrollment `DELETED` — permanently orphaning the
   `REPLACEMENT_PENDING` sample's row and file, with no code path left to
   ever clean it up (reconciliation would report it forever, but nothing
   acts on the report). Fixed by adding
   `BiometricSampleRepository.list_live_for_enrollment` (every sample
   with `status != DELETED`, not just one) and rewriting
   `_advance_deletion` to drain every live sample — `PENDING`, `ACTIVE`,
   `REPLACEMENT_PENDING`, `DELETION_PENDING`, `QUARANTINED` — via a new
   per-sample `_advance_sample_deletion` helper before marking the
   enrollment `DELETED`, and to re-check for live-sample drift rather
   than returning early solely because `enrollment.status` already reads
   `DELETED` (so drift left behind by an earlier partial failure is still
   drained on a later call instead of being permanently invisible).
   Regression test:
   `test_finalize_deletion_drains_stalled_replacement_artifact_too` in
   `test_phase5_stage2_failure_injection.py` — reproduces the stalled
   `REPLACEMENT_PENDING` retirement, then asserts a subsequent enrollment
   deletion removes both the old and new sample's rows and files.
4. **Bulk manifest duplicate-student detection compared raw text, not
   parsed identity.** `zip_security.py`'s `_parse_manifest` deduplicated
   on the manifest's raw `student_profile_id` column text, after already
   parsing it into a `uuid.UUID`. Two rows spelling the same student
   differently — canonical lowercase, uppercase, or
   `{braced}` — parse to the identical `uuid.UUID` value but were treated
   as three different students, allowing a manifest to reference the same
   student more than once undetected. Fixed to dedupe on
   `str(student_profile_id)` (the canonical form of the already-parsed
   value). Test:
   `test_duplicate_student_row_different_uuid_representation_is_rejected`
   in `test_phase5_stage2_zip_security.py`.
5. **Oversized bulk ZIP raised the wrong error class.**
   `bulk_service.py`'s `enroll_from_zip` raised
   `EnrollmentImageTooLargeError` (the *single-image* byte-cap error) when
   `write_bulk_zip_staged` hit `MAX_BULK_ENROLLMENT_ZIP_BYTES` — wrong
   error code/message for an archive-level rejection. Fixed to raise
   `BulkEnrollmentZipTooLargeError`. Test:
   `test_bulk_oversized_zip_returns_413_with_correct_error_code` in
   `test_phase5_stage2_bulk_zip_http.py`.
6. **No compensation existed for a DB/audit failure occurring *after* a
   file was already promoted** in `create_sample`, `replace_sample`
   (`service.py`), and bulk row execution (`bulk_service.py`). Each of
   those three code paths calls `PrivateBiometricStorage.promote()` (an
   irreversible `os.replace` from staging into the `active/` zone) and
   then, in a separate step, runs the transaction that marks the sample
   `ACTIVE` and writes the audit row. Only a failure *during promote
   itself* was ever compensated (`_compensate_failed_promote`, pre-
   existing and correct); a failure in the *subsequent* transaction — the
   file already real and active, the DB write that would record it rolled
   back — left an orphaned file in `active/` with no matching `ACTIVE`
   row, and (for bulk) also left that row's originally-staged file
   undiscarded whenever a row failed for *any* reason during execution,
   not only this one. Fixed by adding
   `_compensate_promoted_file_after_activation_failure` (in both
   `service.py` and, duplicated on purpose per this module's established
   convention, `bulk_service.py`) — re-reads the sample fresh from the
   database (never trusts the in-memory object after a rollback), moves
   the orphaned file out of `active/` via quarantine, purges it, and
   removes the now-meaningless row — wrapped around the final
   activate/audit transaction in all three call sites, and never
   re-raising its own failure (the original error is always what
   propagates; a secondary compensation failure is logged for
   reconciliation instead). Also added
   `self._storage.discard_staged(item.staging_key)` to
   `_execute_rows`'s per-row exception handler so *every* row that fails
   during bulk execution — for any reason, not only this one — has its
   staged file discarded (idempotent/harmless for a row that already got
   as far as promote, since that file has already been moved out of
   staging by then). Five failure-injection tests added to
   `test_phase5_stage2_failure_injection.py`:
   `test_create_sample_activation_failure_after_promote_leaves_no_falsely_active_sample`,
   `test_create_sample_activation_failure_allows_retry_after_fix`,
   `test_replace_sample_activation_failure_preserves_old_active_sample`,
   `test_bulk_activation_failure_after_promote_compensates_and_reports_row_failed`,
   `test_bulk_execution_failure_discards_staged_file_for_every_failed_row`.
7. **An archive-level bulk rejection wrote no audit record at all.**
   `enroll_from_zip` wrote a `BLOCKED` bulk-attempt audit record when
   `_prepare_rows` found row-level problems, but a rejection raised
   directly by `validate_archive` itself — a malformed ZIP, a path-
   traversal member, a missing manifest, and similar archive-level
   failures, all raised *before* any row is ever reached — propagated
   with no audit record at all. Fixed by wrapping the `validate_archive`
   call specifically, writing the same `BLOCKED` bulk-attempt audit
   (aggregate `total_rows`/`enrolled_count` only — no filename, member
   path, or archive content, matching this audit action's existing
   contract exactly) before re-raising the original error unchanged.
   Test: `test_bulk_archive_level_rejection_writes_blocked_audit` in
   `test_phase5_stage2_bulk_zip_http.py` — asserts *exact* equality of
   the recorded `event_metadata`, proving nothing beyond the two
   aggregate counts was ever recorded.
8. **The migration round-trip test assumed `"head" == this stage's own
   revision`, which will break the moment Stage 3 adds a migration.**
   `test_migrations_phase5_stage2.py` ran `command.upgrade(cfg, "head")`
   and then asserted `_current_revision(cfg) == PHASE5_STAGE2_HEAD_REVISION`
   — true only as long as this migration is still the newest one. Fixed
   to: upgrade to the true latest `"head"` first (self-contained,
   matching the Docker test workflow); move *explicitly* to
   `ca8e748dc8f2` for every Stage-2-specific assertion (table presence,
   all three enums' values); downgrade to the Phase 4 head,
   `e1208296dad5` (asserting Stage 2's tables are gone, every earlier-
   phase table and enum is untouched); re-upgrade *specifically* to
   `ca8e748dc8f2` (not `"head"`) and re-assert; and restore the schema to
   the true latest `"head"` in a `finally` block regardless of outcome,
   since every other database-backed test in the session depends on
   tables from every migration — including any Stage 3 adds later —
   existing. This test now remains valid, unmodified, once Stage 3 adds
   its own migration on top.

None of the eight fixes above touch `app/modules/face_recognition/`,
add any inference dependency, or write any code that detects, aligns,
embeds, or matches a face — the Stage-3-scope scan re-run this session
(see "Verification commands" below) confirms this same as it did in the
original session.

---

## Exact Stage 3 starting point

Stage 3 (per `docs/IMPLEMENTATION_PLAN.md`, unchanged by this session) is
responsible for: the first real `FaceDetector`/`FaceEmbedder`/
`FaceMatcher` implementations (YuNet via OpenCV's `FaceDetectorYN`,
per Accepted ADR 0005; embedding model per ADR 0005's still-deferred
licensing resolution), wired against the biometric samples Stage 2 now
stores. Concretely, Stage 3 should:

1. Add `opencv-python-headless` (and `onnxruntime` only if the selected
   embedding-model adapter genuinely needs it) to `backend_v2/pyproject.toml`
   — the first inference dependency this repository will have.
2. Implement `app/modules/face_recognition/`'s `FaceDetector`/
   `FaceEmbedder`/`FaceMatcher` `Protocol`s (Stage 1's contracts,
   untouched since Stage 1) against real model files.
3. Read a student's `ACTIVE` `BiometricSample` via
   `BiometricSampleRepository.get_active_for_enrollment` (already
   present, already used by Stage 2's own replace/delete flows) —
   Stage 3 is the first code path expected to actually open the file at
   `PrivateBiometricStorage.active_path(sample.storage_key)` for
   inference use (Stage 2 never opens a promoted file's contents again
   after promotion, only tracks its metadata).
4. On successful embedding, write `processing_state = PROCESSED` (or
   `PROCESSING_FAILED` on a genuine embedding failure) — the first code
   in this repository ever expected to write anything other than
   `PENDING_PROCESSING` to that column. No schema migration is needed for
   this: both values already exist in the
   `biometric_recognition_processing_state` enum (Stage 2 deliberately
   declared all three values up front for exactly this reason).
5. Add whatever new embedding-storage column(s)/table(s) Stage 3 needs
   (e.g. `EmbeddingVector.values`) via a **new** Alembic migration whose
   parent is `ca8e748dc8f2` — never edit this migration or Stage 2's
   models directly.
6. Leave every Stage 2 API contract, error code, and response schema
   exactly as documented above — Stage 3 is additive.

**No line of Stage 3 (detection, alignment, embedding, matching, or a
recognition-triggered attendance write) was implemented, sketched, or
stubbed in this session.**

---

## Second correction patch (v3) — migration test upgrade/downgrade fix

**Bug, introduced by the v2 correction patch's item 8 above:** the
rewritten `test_phase5_stage2_migration_round_trip` moved from true
latest head to this stage's own revision via `command.upgrade(cfg,
PHASE5_STAGE2_HEAD_REVISION)`. That call is only valid while
`ca8e748dc8f2` is still the true head — i.e., before Stage 3 adds any
migration on top of it. Once Stage 3 adds a migration whose parent is
`ca8e748dc8f2`, this stage's revision becomes an *ancestor* of the true
head reached by the preceding `command.upgrade(cfg, "head")`, so the
correct operation to move from there back to `ca8e748dc8f2` is a
downgrade, not an upgrade.

**Fix:** in `backend_v2/app/tests/test_migrations_phase5_stage2.py`, the
line immediately after the initial `command.upgrade(cfg, "head")` now
reads `command.downgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)`. The later
re-upgrade — from the Phase 4 head back to this stage's own revision,
`command.upgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)` — is unchanged, since
that move is genuinely forward and was already correct. The function's
docstring was tightened to describe the first move as head-relative (a
downgrade once a later stage's migration exists on top, and a no-op only
for as long as Stage 2 happens to still be the true head) rather than
unconditionally "up."

**Scope:** test-only. No application code, migration file, model,
router, or unrelated test was touched. Stage 3 was not started in this
session, same as both prior sessions. No Git operation was performed.

See "Second correction patch (v3) — exact files modified", "Second
correction patch (v3) — verification commands actually run", and "Second
correction patch (v3) — checks unavailable, and precisely why" above for
the full accounting.

---

## Confirmation: Stage 3 was not started

Verified by the Stage-3-scope scan recorded under "Verification commands
actually run" above: no detection/embedding/matching code exists
anywhere in `app/modules/biometric_enrollment/`, and
`app/modules/face_recognition/` is byte-for-byte unchanged from the
Stage 1 checkpoint. No inference dependency was added.
`RecognitionProcessingState.PROCESSED`/`PROCESSING_FAILED` are declared
in the enum but never written by any Stage 2 code path — confirmed by
grep: every `RecognitionProcessingState` write anywhere in
`app/modules/biometric_enrollment/` is `PENDING_PROCESSING`.

## Confirmation: no Git operation was performed

No `git reset`, `restore`, `checkout`, `clean`, `stash`, `commit`,
`branch`, or `tag` command was run this session, and no such command was
run in any prior session in this line of work either. The repository's
pre-existing `.git` history (and the working-tree state `docs/AUDIT.md`
§1.1 already documented as dirty relative to `HEAD`) is untouched beyond
the file changes explicitly listed above.

## Must NOT be redone

- Phase 5 Stage 1's ADR 0005 decision, `face_recognition` contracts, and
  biometric `Settings` fields — unchanged, still correct.
- This checkpoint's database schema, storage layout, lifecycle states,
  authorization decisions, and manifest format — a future session should
  build on these, not redesign them, absent a genuine new requirement
  documented in a new ADR.
- Phase 1-4 migrations, API contracts, and legacy Flask/React code —
  confirmed untouched this session; keep it that way.
