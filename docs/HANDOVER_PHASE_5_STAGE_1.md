# Handover — Rebuild Phase 5, Stage 1 (Provider Decision and Biometric Foundation)

**Status: Stage 1 complete for this checkpoint's scope, including one
correction pass.** ADR 0005 is `Accepted`, the provider-neutral
contracts/protocols/errors exist, `Settings` has a fail-fast Stage 1
configuration surface, `docs/BIOMETRIC_DATA_POLICY.md` exists, and
focused contract/config tests are written. **No detector/embedder/matcher
is implemented, no router exists, no ORM table or migration was added, no
new inference dependency was added, and no model file was downloaded or
vendored.** Runtime verification (pytest/Ruff/mypy/Docker/PostgreSQL)
could not be executed in this sandbox — see "Checks not run" below.
**Stage 2 was not started.**

This document supersedes the version written before the correction pass
described below; every fact in it has been re-verified against the
current repository state, not carried over from the earlier draft.

## Correction pass applied in this session

A later review caught four categories of inaccuracy in the original
Stage 1 delivery. All four are fixed as of this document:

1. **ADR 0005 factual corrections:**
   - GitHub issue `opencv/opencv#21192` ("What is the license for SFace
     model?") is **`Closed`**, not still-open as an earlier draft of the
     ADR stated. Closing an issue is not the same as an explicit
     licensing answer, and no resolving comment is visible in the issue
     itself — the ADR now says exactly that, and additionally notes that
     `opencv/opencv_zoo`'s `models/face_recognition_sface/` directory now
     contains a `LICENSE` file (Apache-2.0 text), which the ADR
     deliberately does **not** treat as a confirmed, independently
     verified grant for the model weight itself (it may simply mirror
     the repository's own top-level license rather than a dedicated
     statement about a weight whose provenance traces to a separate
     upstream project, `zhongyy/SFace`). SFace remains unselected until
     provenance and redistribution rights are independently verified —
     not inferred from a directory-level license file alone.
   - The claim that "face-api.js's own README points users toward a
     replacement library" was mis-sourced. The original
     `justadudewhohacks/face-api.js` package's own npm registry page
     confirms no release since `0.22.2` in March 2020 (accurate, and
     retained). The "points toward a replacement" statement belongs to a
     *different* artifact: the actively-referenced community fork
     `@vladmandic/face-api`'s **own** README states it is "completely
     superseded by" the maintainer's newer library, Human. The ADR now
     attributes that statement correctly to the fork, not the original.
   - **Detector runtime clarified and corrected:** YuNet is loaded through
     OpenCV's DNN/`FaceDetectorYN` API using `opencv-python-headless`.
     The separate `onnxruntime` package is **not** required to run this
     detector — OpenCV's own DNN module parses and executes the YuNet
     `.onnx` file directly through its built-in ONNX importer.
     `onnxruntime` is deferred until (and only if) a selected
     embedding-model adapter genuinely needs it. Every place that
     previously said "OpenCV DNN + ONNX Runtime" as one combined detector
     runtime (the ADR, `docs/IMPLEMENTATION_PLAN.md`, `docs/PROGRESS.md`,
     `backend_v2/README.md`, `app/modules/face_recognition/__init__.py`)
     is corrected.
2. **`MatchResult` invariants strengthened** (`domain.py`) — see
   "Contracts and protocols created" below for the full updated set.
3. **Biometric deletion atomicity corrected** (`docs/BIOMETRIC_DATA_POLICY.md`)
   — removed the incorrect claim that a SQLAlchemy/database transaction
   alone can atomically roll back a filesystem write or delete; replaced
   with the actual mandatory Stage 2 architecture (staged writes,
   `PENDING`/`ACTIVE` states, atomic rename, quarantine, async retryable
   purge, reconciliation).
4. **Handover verification facts corrected** (this document): final test
   counts recalculated below; the earlier "8 pre-existing line-length
   violations" claim is **withdrawn** — it was a false positive in the
   earlier scan's own methodology (`awk`'s `length($0)` on a CRLF file
   includes the trailing `\r` in the count, inflating every such line by
   one character), not a real violation. A CRLF-safe re-scan (Python,
   explicitly stripping `\r\n`/`\n` before measuring) confirms **zero**
   real line-length violations anywhere in the delivered tree. See
   "Verification commands actually run" below.

## What this checkpoint actually is

Built directly on the verified Phase 4 closure baseline (`docs/PROGRESS.md`
"Phase 4 Closure": 311 tests, Ruff format/lint, and mypy all passing
against Docker/PostgreSQL; Alembic head `e1208296dad5`). Work across both
the original delivery and this correction pass:

1. `docs/adr/0005-face-recognition-provider-pending.md` updated from
   `Proposed / Pending` to **`Accepted`**, with a full, sourced comparison
   across all thirteen required criteria, corrected per the section
   above.
2. `backend_v2/app/modules/face_recognition/` created from scratch:
   `domain.py` (typed value objects, invariants strengthened this
   session), `protocols.py` (`FaceDetector`/`FaceEmbedder`/`FaceMatcher`
   Protocols), `errors.py` (`AppError` subclasses), `__init__.py` (locks
   all five Phase 5 stages, dependency wording corrected this session).
3. `backend_v2/app/core/config.py` extended with a `FaceRecognitionProvider`
   enum and eight new `Settings` fields, each fail-fast validated, all
   defaulting to safe/inert values, plus one cross-field rule. Unchanged
   by this correction pass.
4. `backend_v2/app/tests/test_face_recognition_contracts.py` (44 test
   functions / 67 collected cases, final) and `backend_v2/app/tests/test_config.py`'s
   face-recognition section (13 test functions / 29 collected cases,
   unchanged by this pass) — see "Tests" below for the exact breakdown.
5. `docs/BIOMETRIC_DATA_POLICY.md` created, then corrected this session
   (deletion/replacement atomicity architecture).
6. `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`, `docs/PROGRESS.md`,
   `backend_v2/README.md`, both `.env.example` files, and `.gitignore`
   updated in the original delivery; `IMPLEMENTATION_PLAN.md`,
   `PROGRESS.md`, `backend_v2/README.md`, and `__init__.py` additionally
   corrected this session for the detector-runtime wording fix.

## Read first, in order

`docs/HANDOVER_PHASE_4.md` → `docs/adr/0005-face-recognition-provider-pending.md`
→ `docs/BIOMETRIC_DATA_POLICY.md` → this file → `docs/PROGRESS.md`'s
"Phase 5 Stage 1" section (bottom of the file) → `docs/IMPLEMENTATION_PLAN.md`
Phase 5 → the module files themselves (`app/modules/face_recognition/`).

## Selected MVP architecture

**Server-side local Python inference**, running inside `backend_v2`,
behind the provider-neutral `detect`/`embed`/`match` boundary
(`docs/ARCHITECTURE.md` §9), now given concrete typed contracts
(`app/modules/face_recognition/domain.py`) and `Protocol` interfaces
(`protocols.py`). Rejected in comparison: in-browser inference
(face-api.js/TensorFlow.js) and a hosted third-party API — see ADR 0005
for the full thirteen-criterion comparison matrix. In short:

- **In-browser inference rejected** primarily on maintenance-lineage
  grounds (the reference `face-api.js` implementation has not published a
  new release since March 2020, per its own npm registry page; the
  actively-referenced community fork's own README separately states it
  is superseded by a newer library) and testability (no workable
  server-side/CI test story matching this backend's existing pytest
  convention), plus a weaker audit-trail fit.
- **Hosted third-party API rejected** primarily on privacy (raw images or
  face crops must leave the school's infrastructure for every call),
  cost-model mismatch with this project's "Free-Tier Ready" framing, and
  failure coupling (a vendor/network outage becomes an attendance-marking
  outage, which Phase 4's attendance core has never depended on).

### Selected detector direction and licensing status

- **Detector:** YuNet, loaded through OpenCV's DNN/`FaceDetectorYN` API
  using `opencv-python-headless`. **Confirmed MIT-licensed** — the OpenCV
  Zoo's `face_detection_yunet` model directory explicitly states "All
  files in this directory are licensed under MIT License," and the
  OpenCV Zoo repository itself is Apache-2.0. Both are compatible with
  `backend_v2/pyproject.toml`'s own `Proprietary` license declaration.
  **The separate `onnxruntime` package is not required to run this
  detector** — OpenCV's own DNN module parses and executes the YuNet
  `.onnx` file directly via its built-in ONNX importer; `onnxruntime` is
  deferred until (and only if) a selected embedding-model adapter
  genuinely needs it.
- **Embedding model: NOT selected — an explicit, tracked licensing
  blocker.** The model most commonly demonstrated alongside YuNet in
  OpenCV's own tutorials, SFace (`face_recognition_sface`), has an
  unresolved license question. A GitHub issue on `opencv/opencv`
  (issue #21192, "What is the license for SFace model?") states the
  model's license "is not explicitly indicated." **That issue is marked
  `Closed`** (corrected this session — an earlier draft incorrectly
  called it still-open), but closing an issue is not an explicit
  licensing answer, and no resolving comment is visible in it.
  `opencv/opencv_zoo`'s `models/face_recognition_sface/` directory does
  contain a `LICENSE` file (Apache-2.0 text); this ADR does **not** treat
  that alone as a confirmed, independently verified grant for the model
  weight specifically, since it may simply mirror the repository's own
  top-level license rather than a dedicated statement of redistribution
  rights for a weight whose provenance traces to a separate upstream
  project (`zhongyy/SFace`). SFace remains unselected until provenance
  and redistribution rights are independently verified.
- **Device:** CPU-first (`Settings.FACE_INFERENCE_DEVICE` defaults to
  `"cpu"`) — confirmed CPU-only viable per the OpenCV Zoo's own published
  benchmark table. For the detector, GPU is exposed via OpenCV's own
  `cv2.dnn` backend/target selection, but the standard pip
  `opencv-python-headless` wheel is CPU-only — a CUDA-accelerated
  `cv2.dnn` backend requires a custom OpenCV build, not asserted as
  available out of the box. `onnxruntime-gpu` would be a future
  embedding-model adapter's own optional GPU path, not the detector's.
- **No accuracy claim is made anywhere in the ADR or this handover.** The
  WIDER Face benchmark numbers cited in ADR 0005 describe YuNet's
  published performance on a third-party academic dataset, not this
  project's own students, cameras, or classrooms. Real accuracy can only
  be established once Stage 3 implements a real pipeline and Stage 5 runs
  actual verification.

## Contracts and protocols created

All in `backend_v2/app/modules/face_recognition/domain.py` unless noted,
frozen/`extra="forbid"` Pydantic v2 models throughout. Invariants marked
**(strengthened this session)** were added or tightened during the
correction pass.

| Type | Purpose | Key validation |
|---|---|---|
| `ImageDimensions` | width/height in px | both in `[1, 10_000]` |
| `BoundingBox` | face location in px | non-negative x/y; strictly positive width/height |
| `DecodedImage` | detector input | non-empty `pixel_data` |
| `DetectedFace` | one detection result | `confidence` in `[0, 1]`, **explicitly required to be finite (strengthened this session)**; box must fit entirely within `source_image_dimensions` |
| `NormalizedFaceInput` | embedder input | non-empty `pixel_data` |
| `EmbeddingVector` | validated embedding | non-empty; all values finite (no NaN/Inf) |
| `validate_embedding_dimension(vector, *, expected_dimension)` | dimension-mismatch guard | raises `InvalidEmbeddingDimensionError` on mismatch |
| `MatchCandidate` | one candidate + score | `similarity` in `[-1.0, 1.0]`, **explicitly required to be finite (strengthened this session)** (cosine-similarity semantics, never distance) |
| `MatchStatus` | `FOUND`/`UNKNOWN`/`AMBIGUOUS` | — |
| `MatchResult` | matcher outcome | shape-validated per status (`.found()`/`.unknown()`/`.ambiguous()` factories); `FOUND` requires matched ID = best candidate's ID; only `FOUND` may set the matched ID; `FOUND` **must not set `runner_up_candidate` (strengthened this session)**; `AMBIGUOUS` requires both candidates, **its two candidates must reference different students, and `best_candidate.similarity` must be ≥ `runner_up_candidate.similarity` (both strengthened this session)**; `UNKNOWN` must not set a runner-up |
| `ProviderStatus` / `ProviderHealth` | provider health | `provider_name` **stripped and rejected if blank/whitespace-only (strengthened this session)**, ≤100 chars; `detail` ≤200 chars |

`protocols.py`: `FaceDetector.detect(image) -> list[DetectedFace]`,
`FaceEmbedder.embed(face) -> EmbeddingVector`,
`FaceMatcher.match(embedding) -> MatchResult` — all `@runtime_checkable
Protocol`s, deliberately synchronous. No OpenCV/ONNX Runtime/TensorFlow/
hosted-API type appears in any signature. Unchanged by this correction
pass.

`errors.py`: `FaceRecognitionError` (base) →
`FaceProviderUnavailableError` (503), `FaceDetectionFailedError` (422),
`FaceEmbeddingFailedError` (422), `InvalidEmbeddingDimensionError` (422).
Unchanged by this correction pass.

## Configuration fields and validation introduced

Unchanged by this correction pass — see `backend_v2/app/core/config.py`'s
`Settings` class. All eight new fields (`FACE_RECOGNITION_PROVIDER`,
`FACE_DETECTION_MODEL_IDENTIFIER`, `FACE_EMBEDDING_MODEL_IDENTIFIER`,
`FACE_DETECTOR_INPUT_SIZE_PX`, `FACE_EMBEDDING_DIMENSION`,
`FACE_MATCH_THRESHOLD`, `FACE_MATCH_AMBIGUOUS_MARGIN`,
`FACE_INFERENCE_DEVICE`, `BIOMETRIC_STORAGE_ROOT`,
`MAX_ENROLLMENT_IMAGE_BYTES`) remain optional with safe defaults, plus the
one cross-field rule (a non-`none` provider requires both model
identifiers).

## Biometric policy decisions (`docs/BIOMETRIC_DATA_POLICY.md`)

Explicitly framed as **application policy, not legal advice**. Key
decisions unchanged by this session: raw images retained only long
enough to (re-)generate an embedding; embeddings retained only while
enrollment is active; storage outside the public web root; enroll/
replace/delete are admin-only; students may read only their own
enrollment metadata; raw biometric data and embeddings are never
returned by any API; matching results must not directly write
attendance; low-confidence/ambiguous results require human confirmation;
every enrollment/replacement/deletion/recognition decision must be
auditable.

**Corrected this session — atomicity architecture.** The policy
previously implied that reusing the existing `app/db/transaction.py`
pattern alone would make biometric deletion atomic. That is incorrect: a
database transaction can only make database writes atomic, not a
filesystem write/delete alongside it. The policy now documents the
actual mandatory Stage 2 design instead:

- **Enrollment:** write to a private staging path → validate/decode/hash
  → persist a `PENDING` database row → atomically rename the staged file
  to its final path (the real atomicity primitive, not the DB
  transaction) → transition to `ACTIVE` → compensating cleanup and
  periodic reconciliation for anything that fails mid-sequence.
- **Deletion/replacement:** mark `DELETION_PENDING`/`REPLACEMENT_PENDING`
  → move the artifact to a private quarantine location → finalize
  database state → purge the quarantined artifact asynchronously and
  retryably (a background job, not inline with the request) →
  reconciliation for any database/filesystem drift.
- None of this is implemented in Stage 1 — it is a documented design
  constraint for Stage 2.

## Exact files created

- `backend_v2/app/modules/face_recognition/__init__.py`
- `backend_v2/app/modules/face_recognition/domain.py`
- `backend_v2/app/modules/face_recognition/protocols.py`
- `backend_v2/app/modules/face_recognition/errors.py`
- `backend_v2/app/tests/test_face_recognition_contracts.py`
- `docs/BIOMETRIC_DATA_POLICY.md`
- `docs/HANDOVER_PHASE_5_STAGE_1.md` (this file — rewritten during the correction pass)

## Exact files modified

**Original delivery:**
- `backend_v2/app/core/config.py` — `FaceRecognitionProvider` enum, eight new `Settings` fields, six new field validators, one new cross-field `model_validator`.
- `backend_v2/app/tests/test_config.py` — import of `FaceRecognitionProvider`; 13 new test functions (29 collected cases) in a new "Phase 5 Stage 1" section.
- `docs/adr/0005-face-recognition-provider-pending.md` — `Proposed/Pending` → `Accepted`; full comparison matrix and decision added.
- `docs/IMPLEMENTATION_PLAN.md` — Phase 5 section replaced with the five locked stages.
- `docs/ARCHITECTURE.md` — §9 updated to record the accepted decision.
- `docs/PROGRESS.md` — new "Phase 5 Stage 1" dated section appended (CRLF-matched).
- `backend_v2/README.md` — stale Phase 4 status line corrected; new "Face recognition (Phase 5 Stage 1)" section added.
- `backend_v2/.env.example` / root `.env.example` — new commented-out Stage 1 config section.
- `.gitignore` — new pattern excluding `backend_v2`'s future biometric storage root.

**This correction pass, additionally:**
- `docs/adr/0005-face-recognition-provider-pending.md` — GPU-support, dependency/model-size, maintenance-burden, provider-swapability, and licensing table rows corrected; "What is decided" and "Consequences" sections corrected for the detector-runtime and `onnxruntime` facts (see "Correction pass applied" above).
- `backend_v2/app/modules/face_recognition/domain.py` — `MatchResult` invariants strengthened; explicit finite-value checks added to `DetectedFace.confidence` and `MatchCandidate.similarity`; `ProviderHealth.provider_name` now stripped and rejects whitespace-only values.
- `backend_v2/app/modules/face_recognition/__init__.py` — dependency wording corrected (`onnxruntime` decoupled from the detector).
- `backend_v2/app/tests/test_face_recognition_contracts.py` — 8 new test functions (12 additional collected cases) covering the strengthened invariants.
- `docs/IMPLEMENTATION_PLAN.md` — Stage 1/Stage 3 dependency wording corrected.
- `docs/PROGRESS.md` — detector-runtime and issue-status wording corrected (CRLF-safe edit).
- `backend_v2/README.md` — ADR summary line corrected to name the specific, corrected detector runtime.

**Not modified, either pass:** anything under `backend/` or `frontend/`
(legacy Flask/React); `backend_v2/app/db/models.py`;
`backend_v2/alembic/env.py`; any existing migration (`98161483914f`,
`6eeb9420bf8b`, `32819e0a6027`, `e1208296dad5` — all confirmed
byte-for-byte unchanged); any existing API route or response contract;
`backend_v2/pyproject.toml` (confirmed unchanged — no new dependency).

## Tests — final counts

| File | Test functions | Collected cases (with parametrization) |
|---|---|---|
| `app/tests/test_face_recognition_contracts.py` | **44** (36 original + 8 added this session) | **67** (55 original + 12 added this session) |
| `app/tests/test_config.py`, face-recognition section only | **13** (unchanged this session) | **29** (unchanged this session) |

Counts were computed by parsing both files with Python's `ast` module and
multiplying out every `@pytest.mark.parametrize` list, not estimated —
see "Verification commands actually run" below for the exact method.

**Tests added this session (8 new functions / 12 new collected cases),
covering every invariant required by the correction brief:**
- `test_detected_face_confidence_rejects_non_finite_values` (parametrized: NaN, +inf, −inf — 3 cases)
- `test_match_candidate_similarity_rejects_non_finite_values` (parametrized: NaN, +inf, −inf — 3 cases)
- `test_match_result_found_must_not_set_runner_up_candidate`
- `test_match_result_ambiguous_candidates_must_reference_different_students`
- `test_match_result_ambiguous_runner_up_must_not_outscore_best`
- `test_match_result_ambiguous_accepts_equal_similarity_scores` (valid boundary case, not a rejection)
- `test_provider_health_rejects_whitespace_only_provider_name`
- `test_provider_health_strips_surrounding_whitespace_from_provider_name`

**These tests are confirmed syntactically valid (`py_compile`/`compileall`
passed, both individually and for the whole tree) but have NOT been
executed by `pytest` in this sandbox** — `pytest` is not installed and
there is no network access to install it (confirmed below). Their
correctness was instead verified by manual trace-through of every
validator/model-validator branch against every test case; this is
explicitly a substitute for, not equivalent to, an actual test run.

## Verification commands actually run and exact results

All run from `backend_v2/` unless noted; re-run fresh in this correction
pass after all edits above, superseding the original delivery's numbers.

| Command / check | Result |
|---|---|
| `python -m compileall -q app alembic scripts` | **Passed** — exit code 0, zero syntax errors, all 138 `.py` files under `app/`, `alembic/`, `scripts/` |
| AST `ast.parse` of every `.py` file under `app/`, `alembic/`, `scripts/` | **Passed** — 138/138 files parsed with zero `SyntaxError`/`UnicodeDecodeError` |
| Custom AST-based internal `app.*` import-resolution scan | **442/443 resolved.** The one unresolved case, `app/main.py`'s `from app.api.routes import health`, is the same pre-existing false positive documented since `docs/HANDOVER_PHASE_4_STAGE_1.md` — predates this session, unrelated to any Stage 1 change. |
| Line-length scan (Ruff `line-length = 100`), CRLF-safe, across every `.py` file in `backend_v2` | **0 violations, whole tree.** The original delivery's handover claimed 8 pre-existing violations in three untouched Phase 3/4 test files; that claim is **withdrawn** — it was a false positive caused by scanning with `awk`, which does not strip the trailing `\r` from these files' CRLF line endings and so counted every such line as one character longer than it actually is. A corrected scan (Python, explicit `rstrip("\n").rstrip("\r")` before measuring) confirms all eight previously-flagged lines are exactly 100 characters, within the limit. |
| Trailing-whitespace scan across every `.py` file in `backend_v2` | **0 matches**, whole tree. |
| TODO/FIXME/`NotImplementedError` scan (new/modified files) | **0 matches.** |
| Broad-exception scan (`except Exception`/bare `except:`, new/modified files) | **0 matches.** |
| Debug-print scan (new/modified files) | **0 matches** (one pre-existing, unmodified docstring line in `config.py` mentions the *string* `print(settings)` as a rationale example — not an actual print call). |
| Hard-coded-secret scan (new/modified files) | **0 matches** (one pre-existing, unmodified test fixture `_VALID_SECRET = "a" * 40` in `test_config.py` — a synthetic placeholder, not a real credential). |
| Real `.env` inclusion scan (whole repository) | **0 matches** — only `.env.example` files exist. |
| Model-weight/binary scan (whole repository) | **0 matches.** |
| Cache/temp-artifact scan (`__pycache__`, `.pyc`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, leftover scan scripts) | **0 matches** — all removed before packaging. |
| Migration/ORM-registration change scan | **0 changes** — `app/db/models.py`, `alembic/env.py`, and all four existing migration files confirmed byte-for-byte unchanged by checksum; no new `Base` subclass anywhere in `app/modules/face_recognition/` (only Pydantic `BaseModel` subclasses). |
| `pyproject.toml` dependency-list diff | **0 changes** — no `opencv`/`onnx`/`tensorflow`/`insightface`/`deepface`/`dlib`/hosted-API SDK entry anywhere. |
| Stage-1-scope scan (no router registration, no enrollment endpoint, no inference import) | **Confirmed clean** — `face_recognition` does not appear in `app/api/router.py`; no `router`/`APIRouter`/`@router.` code in the module; no `import cv2`/`onnxruntime`/`tensorflow` anywhere in the module (only prose in docstrings describing deferred Stage 2/3 work). |
| Test count recomputation (`ast`-based, both files) | **44 functions / 67 collected cases** in `test_face_recognition_contracts.py`; **13 functions / 29 collected cases** in `test_config.py`'s face-recognition section — see "Tests — final counts" above. |

## Checks not run, and precisely why

- **`pytest` (targeted or full suite):** not installed in this sandbox
  (`ModuleNotFoundError` confirmed via direct `import pytest` from a
  neutral working directory) and `pip install pytest --break-system-packages`
  fails with "No matching distribution found" — no network egress.
- **`ruff format --check app alembic scripts` / `ruff check app alembic scripts`:**
  not run — `ruff` is not installed and cannot be installed (same network
  constraint). Note the CRLF line-length correction above was done with a
  hand-written, CRLF-safe Python scanner mirroring Ruff's `E501` rule at
  `line-length = 100` — it is not a substitute for actually running
  `ruff check`, only the closest available static approximation.
- **`mypy app`:** not run — not installed, same network constraint. In
  particular, this session's new `field_validator`/`model_validator`
  additions to `domain.py` have **not** been type-checked by mypy's
  `strict = true` configuration.
- **PostgreSQL / Docker / Alembic CLI:** not run — Docker is not present
  in this sandbox; no migration was touched this session so there is
  nothing new to migrate, but the existing chain was not re-verified at
  runtime.
- **Any real face-detection/embedding/matching runtime test:** not
  applicable — no such code exists yet in Stage 1 by design.

**No check above is claimed to have passed where it did not actually
run.**

## Known risks

1. **Untested Pydantic/pytest code**, including this session's new
   `MatchResult` invariants — verified only by `py_compile`/AST parsing
   plus manual trace-through, not an actual `pytest` run.
2. **`mypy --strict` unverified**, including this session's new
   validators.
3. **Embedding-model licensing is a real open blocker** — see ADR 0005.
4. **`FACE_EMBEDDING_DIMENSION`/threshold/margin remain structural
   placeholders**, not calibrated values.
5. **`BIOMETRIC_STORAGE_ROOT`'s validator is a narrow, named-segment
   check**, not a comprehensive guarantee.
6. **The Stage 2 atomicity architecture documented in
   `docs/BIOMETRIC_DATA_POLICY.md` is a design requirement, not yet
   implemented or tested code** — Stage 2 must actually build the
   staging/quarantine/reconciliation mechanics described, not just cite
   the document.

## Deferred inference dependencies

Not added in Stage 1. Expected in Stage 3: `opencv-python-headless` (for
the YuNet detector) and its transitive `numpy` dependency. `onnxruntime`
is a **separate, further-deferred** decision — not needed to run the
YuNet detector at all, added only if a selected embedding-model adapter
genuinely requires the standalone ONNX Runtime engine. No other
inference-related dependency (TensorFlow, MTCNN, InsightFace, DeepFace,
dlib, `face_recognition`, any hosted-API SDK) is currently planned.

## Exact Stage 2 starting point

Per `docs/IMPLEMENTATION_PLAN.md` Phase 5, Stage 2 ("Face enrollment and
secure photo ingestion"), not started in this checkpoint:

1. Admin-only enrollment endpoint(s) — create/replace/delete — reusing
   the existing `require_roles`/ownership-check dependency pattern.
2. Validated single-photo and bulk-photo (ZIP) ingestion with per-entry
   path validation performed **before** extraction — the direct fix for
   `docs/AUDIT.md` §2.11/H4's zip-slip pattern.
3. **The staged-write/atomic-rename/quarantine/reconciliation
   architecture now mandated in `docs/BIOMETRIC_DATA_POLICY.md`'s
   "Enrollment, deletion, and replacement atomicity" section** — this is
   new, load-bearing guidance from this correction pass and must actually
   be implemented, not just referenced.
4. Storage under `Settings.BIOMETRIC_STORAGE_ROOT`, with a
   server-generated identifier — never a path derived from an uploaded
   filename.
5. Audit-logged enrollment/replacement/deletion events, reusing the
   existing Phase 4 `AuditLog` model/pattern.
6. Still **no** detection/embedding/matching code, no new inference
   dependency, and no recognition-triggered attendance write — those
   remain Stage 3/4.

## Confirmation: Stage 2 was not started

No enrollment endpoint, no router registration for
`app.modules.face_recognition`, no ORM table, no migration, no bulk
photo/ZIP-handling code, no staging/quarantine/reconciliation code, and
no image-processing code of any kind was written in this checkpoint or
this correction pass — confirmed by the Stage-1-scope scan above.

## Confirmation: no Git operation was performed

No `.git` directory exists in this working copy. No `git init`, `commit`,
`branch`, `tag`, `reset`, `restore`, `checkout`, `clean`, or `stash`
command was run or was possible this session, in either the original
delivery or this correction pass. All pre-existing working-tree state was
left exactly as received.

## Must NOT be redone

- Do not regenerate or restart any Phase 1–4 module.
- Do not edit migration `e1208296dad5` (Phase 4 head) or any earlier
  migration.
- Do not re-litigate ADR 0005's architecture decision (server-side local
  inference, YuNet as detector) — only the deferred embedding-model
  sub-decision remains open.
- Do not re-open the corrections applied this session (issue #21192's
  status, the face-api.js README attribution, the detector/onnxruntime
  decoupling, the `MatchResult` invariants, the biometric atomicity
  architecture, or the test-count/line-length facts) without new evidence
  contradicting them.
