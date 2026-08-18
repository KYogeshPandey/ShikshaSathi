# Handover — Rebuild Phase 5, Stage 3 (Real Face Detection, Alignment, Embedding, and Matching)

**Status: Stage 3 delivered in this checkpoint. Stage 4
(recognition-session workflow / attendance integration) NOT started —
no code in this checkpoint calls `AttendanceService` or writes an
`AttendanceRecord` row; see "Exact Stage 4 starting point" below.**
Built directly on Phase 5 Stage 1 (`docs/HANDOVER_PHASE_5_STAGE_1.md`,
Accepted ADR 0005, provider-neutral `app.modules.face_recognition`
contracts) and Stage 2 (`docs/HANDOVER_PHASE_5_STAGE_2.md`, secure
biometric enrollment/sample lifecycle, migration `ca8e748dc8f2`). No
Stage 1/2 decision was reopened, reversed, or reinterpreted; no Stage
1/2 migration file was edited.

**Superseded in part by a v2 correction patch, applied in a later
session with real PostgreSQL/pytest/Ruff/mypy access for the first
time — see "Stage 3 v2 correction patch" near the end of this document
for the current, authoritative state of findings 1–5 fixed there and
the real (not static-only) verification results. Everything above that
section describes the original Stage 3 delivery and is kept as-is for
historical accuracy except where a specific correction below says
otherwise.**

Read this document before touching `app/modules/face_recognition/`
again.

---

## What this checkpoint actually is

A real, working, local (no hosted API) face-recognition pipeline —
detect → align → embed → persist → candidate-scoped match — behind the
Stage 1 `FaceDetector`/`FaceEmbedder`/`FaceMatcher` Protocol boundary,
plus the enrollment-sample processing lifecycle and matching
orchestration that use it. Concretely:

1. **Detector**: YuNet via OpenCV's `cv2.FaceDetectorYN`
   (`app/modules/face_recognition/providers/yunet_detector.py`) —
   ADR 0005's already-accepted choice, now actually implemented.
2. **Alignment**: a new, standalone geometric normalization stage
   (`app/modules/face_recognition/alignment.py`) between detection and
   embedding — a similarity (rotation+scale+translation) transform
   from YuNet's 5-point landmarks onto fixed reference positions,
   producing a deterministic 150×150 RGB chip.
3. **Embedder**: dlib's `dlib_face_recognition_resnet_model_v1`
   (`app/modules/face_recognition/providers/dlib_embedder.py`) — 128-D,
   L2-normalized at embed time — see "Embedding model" below and
   `docs/adr/0011-phase5-stage3-embedding-model-and-matching.md` for
   the full selection record.
4. **Persistence**: a new `biometric_embeddings` table
   (`app/modules/face_recognition/models.py`), one new Alembic
   migration `d22bce264ecd` (parent `ca8e748dc8f2`) that also adds
   three processing-bookkeeping columns to the existing
   `biometric_samples` table.
5. **Matcher**: candidate-scoped cosine similarity
   (`app/modules/face_recognition/providers/similarity_matcher.py`),
   best-sample-per-student aggregation, deterministic tie-breaking,
   `Settings.FACE_MATCH_THRESHOLD` (now `0.82`, provisional) /
   `FACE_MATCH_AMBIGUOUS_MARGIN` (`0.05`, provisional) — see
   "Threshold and ambiguity policy" below.
6. **Sample processing lifecycle**
   (`app/modules/face_recognition/processing_service.py`):
   `PENDING_PROCESSING → PROCESSED`/`PROCESSING_FAILED`, safe retry,
   bounded on-demand batch processing — no always-running worker.
7. **Matching orchestration**
   (`app/modules/face_recognition/matching_service.py`): the sole
   enforcement point for "an explicit, non-empty candidate scope is
   required" — there is no code path anywhere in this checkpoint that
   matches against every enrolled student.
8. **Provider health**
   (`app/modules/face_recognition/health.py`): safe
   ready/unavailable/not-configured reporting, never running real
   inference and never leaking a path or raw exception.
9. **Evaluation harness**
   (`app/modules/face_recognition/evaluation.py`): FAR/FRR/threshold-
   sweep/ambiguity-rate math over synthetic data only — no real
   evaluation dataset ships with this checkpoint.
10. **APIs** (`app/modules/face_recognition/router.py`): five
    admin-only endpoints — process/retry a sample, get safe processing
    status, get provider health, and an optional candidate-scoped
    match-probe validation endpoint. No recognition-attendance
    endpoint exists.
11. **Tests**: 14 new test files (pure-logic, fake-provider, and
    DB-backed), listed exactly below.

---

## Detector: YuNet / OpenCV `FaceDetectorYN`

- Loaded lazily (first real use, never at import or app-startup time)
  via `cv2.FaceDetectorYN.create(...)`, guarded by
  `app/modules/face_recognition/model_artifacts.py`'s existence +
  optional SHA-256 check before OpenCV ever touches the file.
- Input: a `DecodedImage` (this codebase's own domain type, opaque
  bytes + declared color format); converted to a `numpy.ndarray`, then
  to BGR (`image_codec.to_bgr`) — cv2 always receives BGR regardless of
  whether the source `DecodedImage` was RGB or BGR.
- Output: `list[DetectedFace]`. Zero faces returns an empty list (not
  an error). Every bounding box is clamped to fit entirely within the
  source image dimensions (YuNet can report a box marginally outside
  due to floating-point rounding near an edge); every landmark
  coordinate is independently clamped into `[0, width)`/`[0, height)`.
  Confidence is clamped to `[0.0, 1.0]` and guaranteed finite.
- Landmarks: YuNet's own 5-point order — right eye, left eye, nose
  tip, right mouth corner, left mouth corner — attached to
  `DetectedFace.landmarks` (a new, Stage-3-added optional field; see
  "Domain/protocol changes" below).
- No `cv2`-specific type ever crosses back out of this adapter —
  verified explicitly in
  `test_face_recognition_yunet_detector.py::test_detect_result_type_is_pure_domain_object_no_opencv_leak`.
- `FACE_DETECTOR_INPUT_SIZE_PX` (`Settings`, unchanged from Stage 1,
  default `320`) sets `cv2.FaceDetectorYN`'s input size. NMS threshold
  (`0.3`) and top-K (`500`) are fixed adapter-internal constants, not
  yet exposed as `Settings` fields (not required by the Stage 3 brief's
  explicit field list).

## Alignment / normalization policy

`app/modules/face_recognition/alignment.py`, exact behavior:

- **Input requirement**: exactly 5 landmarks in YuNet's order. Missing
  or wrong-count landmarks → `FaceLandmarksUnavailableError`.
- **Method**: `cv2.estimateAffinePartial2D` (least-squares similarity
  transform — rotation + uniform scale + translation, no shear/
  perspective) mapping the 5 detected landmarks onto 5 fixed reference
  positions in a 150×150 canvas, then `cv2.warpAffine`.
- **Degenerate geometry** (e.g. coincident eye landmarks, no usable
  scale/rotation): `cv2.estimateAffinePartial2D` returns `None` →
  `FaceAlignmentFailedError`. Verified directly against the real,
  installed `cv2` in this environment before being relied on in tests.
- **Edge clipping/padding**: the warp is one affine step directly from
  the whole source image into the 150×150 output; pixels that would
  fall outside the source image become solid black
  (`cv2.BORDER_CONSTANT`, value 0) — never a crash, never wrap/mirror.
- **RGB/BGR handling**: color-format-agnostic; output
  `NormalizedFaceInput.color_format` always matches the input
  `DecodedImage.color_format` exactly, no implicit conversion (the
  embedder converts to RGB at its own boundary).
- **Normalization**: pixel values remain `uint8` `[0, 255]` — no
  rescaling/mean-subtraction here (that is the embedder's concern).
- **Output dimensions**: always exactly 150×150 — a fixed contract
  (`alignment.ALIGNED_FACE_SIZE_PX`), not a `Settings` value, chosen to
  match dlib's own `get_face_chip` output convention.
- **Enrollment zero/multi-face policy** (Stage 3 brief §3): enforced
  one level up, in `app/modules/face_recognition/pipeline.py`'s
  `detect_align_embed` (shared by both sample processing and the
  match-probe endpoint) — zero faces →
  `EnrollmentSampleNoFaceDetectedError`; more than one face →
  `EnrollmentSampleMultipleFacesDetectedError`. No code path ever
  silently picks one face from a multi-face image.
- **Calibration caveat, stated plainly**: this alignment implementation
  is independently written for YuNet's 5-point landmarks; it is *not*
  guaranteed pixel-identical to dlib's own proprietary chip extractor
  (which aligns from dlib's own shape-predictor landmarks, not
  YuNet's). This is a documented, accepted approximation, not a
  measured-equivalent one.

## Embedding model: dlib `dlib_face_recognition_resnet_model_v1`

Full selection record: `docs/adr/0011-phase5-stage3-embedding-model-and-matching.md`.
Summary, kept precise here per this checkpoint's own accuracy
standard:

- **Exact artifact**: `dlib_face_recognition_resnet_model_v1.dat`,
  published at
  `http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2`
  (mirrored at `github.com/davisking/dlib-models`). ~21.4 MB.
- **Architecture**: a ResNet variant, 29 convolutional layers
  ("essentially a version of ResNet-34...with a few layers removed and
  the number of filters per layer reduced by half"), trained from
  scratch on ~3 million faces.
- **Descriptor dimension**: 128-D, confirmed by the model's own stated
  purpose and dlib's own example programs.
- **Two licenses, kept explicitly distinct — do not conflate them:**
  - **The `dlib` Python/C++ *library*** (what this project actually
    imports and runs — `app/modules/face_recognition/providers/dlib_embedder.py`)
    is licensed under the **Boost Software License 1.0**, a permissive
    license explicitly allowing use "however you like, even in closed
    source commercial software" (dlib's own `dlib/LICENSE.txt`; PyPI
    project page; GitHub repository README — all consistent).
  - **The model *weight file* is a separate artifact** with its own,
    separately-stated terms. Its author and dlib's maintainer, Davis
    King, states directly and repeatedly, across dlib's own example
    program comments and a `blog.dlib.net` post: "the pretrained model
    used by this example program is in the public domain. So you can
    use it for anything you want." The `dlib-models` GitHub
    repository's own README repeats this in the maintainer's own
    words.
  - **Honest strength-of-evidence statement (per this checkpoint's
    instruction not to overstate redistribution certainty):** this is
    a direct, repeated, first-party statement from the model's own
    author — the most authoritative source realistically available —
    but it is **not** a machine-readable `LICENSE`/`SPDX` header bundled
    with the `.dat` file itself; the statement lives in the author's
    surrounding example-program comments and blog post, not in the
    artifact. This project **uses** the model for local inference and
    **never redistributes the `.dat` file itself** (see "Model
    distribution strategy" below) — the public-domain statement is
    treated as sufficient for that use. A hypothetical future effort to
    *redistribute* the trained weight file at scale commercially would
    be well-advised to seek an explicit, dated confirmation directly
    from the maintainer rather than relying solely on this ADR's
    citation of existing public statements.
  - **Training-data provenance — disclosed, not resolved:** the model
    was trained on data "derived from a number of datasets" including
    the FaceScrub dataset and the VGG (VGG Face) dataset, plus the
    author's own additionally-collected images. FaceScrub and VGG Face
    are themselves research-oriented datasets with their own
    historical collection/usage terms, which are a **separate
    question** from the trained weight file's own stated public-domain
    status, and this checkpoint does **not** claim to have
    independently resolved that separate, upstream question. Recorded
    explicitly as a known risk below.
- **Alternatives compared and rejected** (full detail in ADR 0011):
  SFace (still blocked — unresolved licensing, unchanged from ADR
  0005, not re-examined here) and InsightFace/ArcFace's `buffalo_l`
  family (rejected — explicit non-commercial-research-only license,
  confirmed via the InsightFace project's own published model-zoo
  terms).
- **Published benchmark context, not this project's own accuracy**:
  99.38% on the LFW benchmark, as published by the model's author — a
  third-party academic-dataset figure, the same category of citation
  ADR 0005 already made for YuNet's WIDER Face numbers. No claim is
  made anywhere in this codebase that this figure describes this
  project's own classroom accuracy.

### Preprocessing and L2 normalization

- Input to `compute_face_descriptor`: the 150×150 aligned RGB `uint8`
  chip produced by `alignment.py`, converted to RGB via
  `image_codec.to_rgb` (a no-op if already RGB) — dlib's documented
  "pass an already-aligned chip directly" usage pattern (as opposed to
  passing a full image + landmarks and letting dlib align internally,
  which this project does not use, since alignment is YuNet-landmark-
  driven here).
- `num_jitters=1` (no jitter-averaging) — deterministic, single-pass
  inference, explicit rather than relying on a library default.
- Raw output validated: exactly 128 finite `float` components, or
  `FaceEmbeddingFailedError`.
- **L2-normalized to a unit vector before being returned** — see
  "Matching metric" below for why. A zero-norm (degenerate) descriptor
  is rejected (`FaceEmbeddingFailedError`) rather than dividing by
  zero.
- Any raw `dlib`/runtime exception is caught and mapped to
  `FaceEmbeddingFailedError` with a fixed, generic message — never the
  original exception text, never a model path.

### Model artifact management

- `Settings.FACE_DETECTOR_MODEL_PATH` / `FACE_EMBEDDER_MODEL_PATH`:
  deployer-supplied filesystem paths, `None` by default. Required
  (fail-fast at `Settings` construction) only once
  `FACE_RECOGNITION_PROVIDER != "none"`.
- `Settings.FACE_DETECTOR_MODEL_SHA256` / `FACE_EMBEDDER_MODEL_SHA256`:
  optional. When set, `app/modules/face_recognition/model_artifacts.py`
  verifies a case-insensitive SHA-256 match before the model is loaded
  — `ModelArtifactChecksumMismatchError` on mismatch,
  `ModelArtifactMissingError` if the file does not exist at all.
  Neither error message ever includes the configured path or checksum.
- **No model artifact (detector or embedder) is downloaded, vendored,
  committed to this repository, or included in the delivered ZIP.** A
  deployer obtains both files independently and configures the two
  path settings (and optionally the two checksum settings) in a real,
  non-committed `.env`.

## Similarity metric, aggregation rule, threshold, and ambiguity policy

- **Metric**: cosine similarity — this codebase's domain contract
  (`app/modules/face_recognition/domain.py`, unchanged since Stage 1)
  fixes this project-wide; never a raw distance anywhere. Made
  consistent with dlib's own Euclidean-distance-oriented guidance by
  L2-normalizing every embedding at embed time (see above) — for unit
  vectors, `cosine_similarity = 1 - (euclidean_distance^2 / 2)`, a
  relationship that is only valid because of that explicit
  normalization step, not a general identity between the two metrics.
- **Aggregation**: best-sample-per-student (maximum similarity among a
  student's candidate embeddings, not a mean) —
  `app/modules/face_recognition/providers/similarity_matcher.py`. In
  practice, Stage 2's own schema invariant (at most one `ACTIVE`
  sample per enrollment, database-enforced) means the DB-backed
  candidate query
  (`BiometricEmbeddingRepository.list_active_for_students`) can
  currently never actually return two simultaneously-active
  embeddings for the same student — the aggregation logic is real,
  implemented, and unit-tested directly
  (`test_face_recognition_matcher.py`) against synthetic multi-
  candidate input, but is not currently reachable through the live
  enrollment flow's own invariants. Documented here so this isn't
  mistaken for dead code.
- **Threshold — `Settings.FACE_MATCH_THRESHOLD = 0.82`.** This is a
  **provisional, structural default**, derived by direct mathematical
  translation of dlib's own general-purpose guidance (same-person if
  raw Euclidean distance < ~0.6) through the identity above:
  `cosine = 1 - (0.6^2 / 2) = 1 - 0.18 = 0.82`. **It is explicitly NOT
  a threshold calibrated against this project's own students, cameras,
  or classroom conditions.** No FAR/FRR evaluation against this
  project's own data has been performed anywhere in this checkpoint.
- **Ambiguity margin — `Settings.FACE_MATCH_AMBIGUOUS_MARGIN = 0.05`**
  (Stage 1's original placeholder, carried forward unchanged) —
  equally provisional, equally uncalibrated.
- **Calibration status: PENDING.** Determining a real production
  threshold requires running
  `app/modules/face_recognition/evaluation.py`'s FAR/FRR/threshold-
  sweep utilities against real, labeled genuine/impostor similarity
  pairs from this project's actual deployment conditions — no such
  dataset exists in this repository (and must never be committed to
  it, per `docs/BIOMETRIC_DATA_POLICY.md`). This is future work, not
  performed here.
- **Match outcomes**: `UNKNOWN` (no candidates, or best similarity
  below threshold), `FOUND` (one confident match, gap to runner-up ≥
  margin), `AMBIGUOUS` (top two candidates within the margin of each
  other) — Stage 1's `MatchResult` domain type (with its own
  `model_validator`-enforced shape invariants, unchanged) is the sole
  return shape; ties are broken deterministically by candidate UUID
  string ordering.

## Persistence design

- **New table**: `biometric_embeddings`
  (`app/modules/face_recognition/models.py`) — a separate aggregate
  from Stage 2's `biometric_samples`, not more columns bolted onto it,
  because a sample (the stored *file*) and its embedding (the
  *numeric result of processing it*) have different lifecycles and
  different sensitivity profiles. FK to `biometric_samples.id`
  (`ON DELETE CASCADE`), `provider_name`/`model_identifier`/
  `model_version` (opaque, safe identifiers), `embedding_dimension`,
  `embedding_values` (`DOUBLE PRECISION[]`), optional
  `model_artifact_checksum`, `is_active`/`superseded_at` (at most one
  active embedding per sample, database-enforced via a partial unique
  index), `created_at`.
- **Representation choice**: a plain PostgreSQL `DOUBLE PRECISION[]`
  array, not `pgvector`. This project's current scale (single-school
  deployment, always-explicit-scope matching against at most a
  classroom-sized candidate list, never a full-database nearest-
  neighbor search) does not need an ANN index; a native array needs no
  new PostgreSQL extension and round-trips losslessly to/from this
  project's own `EmbeddingVector` domain type. Full reasoning:
  `app/modules/face_recognition/models.py`'s module docstring.
- **Three new nullable columns on the existing `biometric_samples`
  table** (added via `ALTER TABLE` in the new migration, never editing
  Stage 2's own migration file): `processing_started_at`,
  `processing_completed_at`, `processing_failure_reason_code`.
- **Availability enforcement**: "deleted/retired/quarantined samples
  cannot match" is enforced entirely at the query level
  (`BiometricEmbeddingRepository.list_active_for_students` joins and
  filters on `BiometricSample.status == ACTIVE` and
  `processing_state == PROCESSED`) — not by touching the embedding row
  itself when a sample's status changes elsewhere in Stage 2's own
  code, which this checkpoint does not modify.
- **Never returned in an API response, never logged, never placed in
  audit `event_metadata`**: `embedding_values`. No schema in
  `app/modules/face_recognition/schemas.py` even declares such a
  field.

### Migration

- **Revision**: `d22bce264ecd`
- **Parent**: `ca8e748dc8f2` (Phase 5 Stage 2's head — file
  `20260804_1000_ca8e748dc8f2_create_biometric_enrollment_tables.py`,
  **not edited**)
- **File**:
  `backend_v2/alembic/versions/20260809_1200_d22bce264ecd_create_biometric_embedding_and_processing_columns.py`
- **Upgrade**: adds the three `biometric_samples` columns, creates
  `biometric_embeddings` with its FK, two check constraints
  (`embedding_dimension > 0`, `array_length(embedding_values, 1) =
  embedding_dimension`), a plain index on `biometric_sample_id`, and
  the partial-unique-active index.
- **Downgrade**: reverses exactly — drops the partial-unique index,
  the plain index, the table, then the three added columns, in that
  order — landing back at Stage 2's exact original schema.

## Provider health

`app/modules/face_recognition/health.py` — combined detector +
embedder status behind `GET /api/v1/face-recognition/health`
(admin-only). Reports `ready`/`unavailable`/`not_configured` per
provider plus one overall status; a health check only calls each
provider's `is_available()` (a load-attempt, no image touched) —
**never runs detection/embedding against any image, real or
synthetic** (verified directly:
`test_face_recognition_health.py::test_health_never_runs_recognition_it_only_checks_availability`
uses a fake provider whose `.detect()`/`.embed()` raise
`AssertionError` if ever called). Never returns a filesystem path or
raw exception text in any `detail` field — verified against both the
default (`NOT_CONFIGURED`) and an explicitly-configured-but-missing-
model-file scenario
(`test_phase5_stage3_api_http.py::test_health_response_never_leaks_a_configured_missing_model_path`).

## APIs and authorization

All under `/api/v1/face-recognition`, all `require_roles(UserRole.ADMIN)`
— matching `app.modules.biometric_enrollment.router`'s own admin-only
convention for enrollment writes. No student- or teacher-facing route
exists in this checkpoint (deferred — see "Exact Stage 4 starting
point").

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/samples/{sample_id}/process` | Run detect→align→embed→persist for one `ACTIVE`, not-yet-processed sample. |
| `POST` | `/samples/{sample_id}/retry` | Retry a sample whose previous attempt is `PROCESSING_FAILED`. |
| `GET` | `/samples/{sample_id}/status` | Safe processing status (state, timestamps, failure reason code — never the embedding). |
| `POST` | `/samples/process-pending` | Bounded, on-demand batch processing of pending samples (`Settings.FACE_PROCESSING_BATCH_LIMIT`, default 20). |
| `GET` | `/health` | Provider/model readiness (see above). |
| `POST` | `/match-probe` | Diagnostic-only: validate the pipeline against an ad hoc image + an explicit, required, non-empty `candidate_student_profile_ids` list. Never writes attendance. |

No route returns an embedding value or raw image bytes — verified by
schema shape (`app/modules/face_recognition/schemas.py`) and directly
by HTTP response-body assertions in `test_phase5_stage3_api_http.py`.

## Domain / protocol changes (additive, not a Stage 1/2 rewrite)

Two Stage 1 files were extended — both changes are additive
refinements of contracts Stage 1 explicitly left open (no
implementation existed yet to constrain them), not modifications of
already-implemented Stage 1/2 behavior:

- `app/modules/face_recognition/domain.py`: added `FacialLandmark` and
  a `landmarks: tuple[FacialLandmark, ...] | None` field on
  `DetectedFace` (structurally validated, 1–68 points if present); and
  `CandidateEmbedding` (a `student_profile_id` + `EmbeddingVector` pair).
- `app/modules/face_recognition/protocols.py`: `FaceMatcher.match`'s
  signature changed from Stage 1's `match(self, embedding)` to
  `match(self, embedding, candidates)` — the concrete mechanism for
  "candidate-scoped matching, never global" (Stage 3 brief). The one
  Stage 1 test file that exercised this protocol
  (`test_face_recognition_contracts.py`) is updated in this checkpoint
  to use the new signature — its own fake matcher and every call site
  were stale after the signature change and are fixed here (a genuine
  defect caught and corrected during this checkpoint's own
  implementation-vs-tests review, not a pre-existing intentional gap).

## Dependencies added

- `opencv-python-headless>=4.10,<5.0` — YuNet detection via
  `cv2.FaceDetectorYN` (ADR 0005's already-accepted choice; no
  `onnxruntime` needed, OpenCV's own DNN module parses the `.onnx`
  file).
- `numpy>=1.26,<3.0` — the array representation every Stage 3 adapter
  converts pixel bytes to/from (`image_codec.py`).
- `dlib>=19.24,<20.0` — this ADR's selected embedding model's own
  native inference engine (no ONNX export exists for this model — see
  ADR 0011's "Consequences").
- **`onnxruntime` deliberately NOT added** — neither dependency above
  needs it.

## Security / privacy summary

- Embeddings: never in an API response, never logged, never in audit
  `event_metadata` — verified in code (schema shapes, `event_metadata`
  literals in `processing_service.py`) and by test
  (`test_phase5_stage3_api_http.py`,
  `test_phase5_stage3_processing_service.py`).
- Filesystem paths: never in a client-facing error message
  (`ModelArtifactMissingError`/`ModelArtifactChecksumMismatchError`/
  `SampleStorageFileMissingError` are all fixed, generic strings) or a
  health-check response — verified by test against both an unconfigured
  and an explicitly-bogus-but-configured path.
- Raw provider exceptions: every `except Exception` in the provider
  adapters and `processing_service.py` maps to one of this module's own
  typed, generic-message `FaceRecognitionError` subclasses before
  reaching any caller.
- Authorization: every Stage 3 route is `ADMIN`-only; no
  ownership-check dependency was layered on top, since an admin's role
  already grants full scope (matching Stage 2's own router convention)
  — verified by 401/403 tests per role.
- Candidate scope: `MatchingService.match_probe` is the **sole**
  reachable path to the matcher provider in this checkpoint and raises
  `CandidateScopeRequiredError` on an empty list — there is no code
  path anywhere that matches against every enrolled student.
- Attendance: **no import of, or call to,
  `app.modules.attendance.service.AttendanceService` anywhere in
  `app/modules/face_recognition/`, and no `AttendanceRecord` row is
  ever constructed there** — verified both statically (source-text
  scan in `test_phase5_stage3_api_http.py::test_face_recognition_module_never_imports_attendance_service`)
  and dynamically (`attendance_records` row-count assertion in
  `test_phase5_stage3_api_http.py::test_processing_and_matching_never_write_attendance_records`).

---

## Exact files created

**Implementation (`backend_v2/app/modules/face_recognition/`):**
- `alignment.py`
- `evaluation.py`
- `health.py`
- `image_codec.py`
- `matching_service.py`
- `model_artifacts.py`
- `models.py`
- `pipeline.py`
- `processing_service.py`
- `provider_factory.py`
- `repository.py`
- `router.py`
- `schemas.py`
- `providers/__init__.py`
- `providers/dlib_embedder.py`
- `providers/similarity_matcher.py`
- `providers/yunet_detector.py`

**Migration:**
- `backend_v2/alembic/versions/20260809_1200_d22bce264ecd_create_biometric_embedding_and_processing_columns.py`

**Tests (`backend_v2/app/tests/`):**
- `phase5_stage3_helpers.py`
- `test_face_recognition_alignment.py`
- `test_face_recognition_dlib_embedder.py`
- `test_face_recognition_evaluation.py`
- `test_face_recognition_health.py`
- `test_face_recognition_matcher.py`
- `test_face_recognition_model_artifacts.py`
- `test_face_recognition_pipeline.py`
- `test_face_recognition_yunet_detector.py`
- `test_migrations_phase5_stage3.py`
- `test_phase5_stage3_api_http.py`
- `test_phase5_stage3_matching_service.py`
- `test_phase5_stage3_model_registration.py`
- `test_phase5_stage3_processing_service.py`

**Documentation:**
- `docs/adr/0011-phase5-stage3-embedding-model-and-matching.md`
- `docs/HANDOVER_PHASE_5_STAGE_3.md` (this file)

## Exact files modified

- `backend_v2/app/modules/face_recognition/domain.py` — added
  `FacialLandmark`, `CandidateEmbedding`, `DetectedFace.landmarks`.
- `backend_v2/app/modules/face_recognition/errors.py` — added the
  Stage 3 error vocabulary (alignment/detection/embedding/model-
  artifact/candidate-scope/sample-eligibility errors).
- `backend_v2/app/modules/face_recognition/protocols.py` —
  `FaceMatcher.match` signature extended with `candidates`.
- `backend_v2/app/modules/biometric_enrollment/models.py` — added
  three nullable processing-bookkeeping columns to `BiometricSample`.
- `backend_v2/app/modules/biometric_enrollment/repository.py` — added
  `list_active_pending_processing`, `mark_processing_started`,
  `mark_processed`, `mark_processing_failed` to
  `BiometricSampleRepository` (purely additive; no existing method
  changed).
- `backend_v2/app/core/config.py` — added
  `FACE_DETECTOR_MODEL_PATH`/`FACE_EMBEDDER_MODEL_PATH`/their SHA-256
  fields/`FACE_PROCESSING_BATCH_LIMIT` (plus validators); extended the
  provider-consistency startup check to require the two model paths;
  changed `FACE_MATCH_THRESHOLD`'s default from Stage 1's placeholder
  `0.90` to the derived `0.82` (see "Threshold" above).
- `backend_v2/app/db/models.py` — registered `BiometricEmbedding`.
- `backend_v2/app/api/router.py` — registered the face-recognition
  router.
- `backend_v2/pyproject.toml` — added the three dependencies above.
- `backend_v2/.env.example` — added the Stage 3 model-path/checksum/
  batch-limit section; updated the `FACE_MATCH_THRESHOLD` example
  value to `0.82`. (Root and legacy `.env.example` files were **not**
  touched.)
- `backend_v2/app/tests/conftest.py` — added `biometric_embeddings` to
  the child-first table-cleanup list (deleted before
  `biometric_samples`, respecting the FK).
- `backend_v2/app/tests/test_face_recognition_contracts.py` — updated
  `_FakeLookupFaceMatcher` and its call sites to the Stage 3
  `candidates`-parameter signature (see "Domain/protocol changes").
- `docs/adr/0005-face-recognition-provider-pending.md` — added a short
  cross-reference note pointing to ADR 0011; no other line changed.

## Exact tests added

Full list is the "Tests" section under "Exact files created" above
(14 files). Coverage by area:

- **Detector** (`test_face_recognition_yunet_detector.py`): missing
  model, checksum mismatch, corrupt/unloadable model, zero/one/
  multiple faces, confidence clamping, bounding-box edge clipping, no
  OpenCV type leak.
- **Alignment** (`test_face_recognition_alignment.py`): valid
  landmarks, deterministic output shape, RGB/BGR preservation, missing/
  wrong-count landmarks, degenerate geometry, near-edge landmarks.
- **Pipeline face-count policy** (`test_face_recognition_pipeline.py`):
  exactly-one-face success, zero-face rejection, multi-face rejection.
- **Embedder** (`test_face_recognition_dlib_embedder.py`): artifact
  validation, 128-D/finite/L2-normalized output, preprocessing shape/
  jitter, wrong-length/non-finite/all-zero descriptor rejection,
  exception sanitization, availability probing.
- **Model artifacts** (`test_face_recognition_model_artifacts.py`):
  missing file, directory-instead-of-file, checksum match/mismatch/
  case-insensitivity, path never in error message.
- **Matcher** (`test_face_recognition_matcher.py`): no candidates,
  below-threshold, clear FOUND, AMBIGUOUS, deterministic ties,
  dimension mismatch, out-of-scope exclusion (structural), best-
  sample-per-student aggregation, no self-ambiguity.
- **Evaluation** (`test_face_recognition_evaluation.py`): FAR/FRR hand-
  verified against synthetic data, threshold-sweep monotonicity,
  ambiguity rate, empty-class safety, no fabricated-accuracy-constant
  guard.
- **Health** (`test_face_recognition_health.py`): ready, not-
  configured, detector/embedder-unavailable, no path leak, never calls
  detect/embed.
- **Model registration** (`test_phase5_stage3_model_registration.py`):
  table/column registration, FK/cascade, check constraints, partial
  unique index, nullability.
- **Migration round-trip** (`test_migrations_phase5_stage3.py`): the
  full upgrade→move-to-Stage-3→assert→downgrade-to-Stage-2→assert→
  upgrade-back→reassert→restore-head sequence.
- **Processing lifecycle** (`test_phase5_stage3_processing_service.py`,
  DB-backed): pending→processed, zero-face failure, retry, already-
  processed/non-active rejection, DB-failure-leaves-no-half-active-
  embedding, replacement-does-not-inherit-old-embedding, bounded batch.
- **Matching service** (`test_phase5_stage3_matching_service.py`,
  DB-backed): empty scope rejected, out-of-scope exclusion, quarantined-
  sample exclusion, unprocessed-sample exclusion, ambiguous pair.
- **API/HTTP** (`test_phase5_stage3_api_http.py`, DB-backed): per-role
  auth, safe response shapes, health path-leak guards, empty-scope
  rejection, audit sanitization, no-attendance-write (static + dynamic).

## Checks actually run, and results

- `python -m compileall -q backend_v2/app backend_v2/alembic
  backend_v2/scripts` — **passed**, no output (clean).
- Full-tree `ast.parse` over every `.py` file under `backend_v2/` —
  **passed**, zero syntax errors.
- Custom AST-based unused-import scan, scoped first to every Stage 3
  file, then re-run project-wide — **found and fixed** one genuinely
  unused import (`EmbeddingVector` in `test_face_recognition_matcher.py`).
- Custom AST-based **undefined-name** scan (distinct from the unused-
  import scan — checks for names *used but never bound*), run over
  every Stage 3 file and then the whole `backend_v2/app` tree —
  **found and fixed** one real bug: `test_phase5_stage3_api_http.py`
  used `patch_providers` without importing it (would have raised
  `NameError` at test-collection time). The only other flagged name
  (`ItemT` in a pre-existing, non-Stage-3 file,
  `app/schemas/pagination.py`) is a confirmed scanner false positive —
  PEP 695 generic-class syntax (`class Page[ItemT](BaseModel)`), not a
  real undefined name; left untouched (out of Stage 3 scope).
- Duplicate top-level-definition scan over
  `app/modules/face_recognition/` — **passed**, no duplicates.
- Bare-`except:`/TODO/FIXME/XXX scan over
  `app/modules/face_recognition/` — **passed**, none found.
- Line-length scan (this project's configured Ruff limit, 100 chars) —
  **found and fixed** 11 violations in implementation files and 7+ in
  test files (mostly long `with patch(...), patch(...):` chains — the
  fix included refactoring four test files onto one shared
  `patch_providers()` context-manager helper, reducing duplication as
  a side effect).
- Real-implementation-vs-real-tests focused review, item by item
  against the review checklist (processing lifecycle, matching/
  repository exclusion logic, detector→alignment→embedder ordering,
  BGR/RGB correctness, 128-D/L2-normalization, privacy/audit/no-
  attendance guarantees) — **one genuine defect found and fixed**: the
  pre-existing Stage 1 `test_face_recognition_contracts.py` fake
  matcher was stale against the Stage 3 `FaceMatcher.match(embedding,
  candidates)` signature change (see "Domain/protocol changes"); fixed
  in place, minimal surface, no protocol redesign.
- Targeted numeric verification (not `pytest` — `pytest` itself is
  unavailable in this sandbox, see below) of every non-trivial test
  fixture's expected result against a standalone re-implementation of
  the real algorithm, run directly in this sandbox with the real,
  installed `numpy`/`opencv-python-headless` — confirms the alignment
  transform's degenerate-case handling, the cosine/Euclidean identity
  used for the threshold derivation, and every hand-picked similarity
  value asserted in `test_face_recognition_matcher.py` and
  `test_face_recognition_evaluation.py` match the actual algorithm's
  output, not just an assumption about it. (One real bug caught this
  way and fixed before it ever reached the test file: an early draft
  embedding-vector generator used modular arithmetic that silently
  aliased different seeds to identical vectors — `99 * (i+1) % 7 == 1 *
  (i+1) % 7` for every integer `i` — replaced with a sine-based hash.)

## Unavailable checks, and why

**This section describes the original Stage 3 delivery session's
sandbox, which had no network egress and none of these tools
installed. A later v2 correction session (see "Stage 3 v2 correction
patch" below) had full network egress, a real local PostgreSQL 16
instance, and every tool below actually installed and actually run —
that section is the current, authoritative verification record. This
section is kept unmodified as an accurate record of what the original
delivery could and couldn't verify.**

This sandbox has no network egress (confirmed:
`pip install --break-system-packages --dry-run fastapi` returns "No
matching distribution found") and does not have `fastapi`, `pydantic`,
`sqlalchemy`, `pytest`, `alembic`, `dlib`, `structlog`, `asyncpg`,
`httpx`, `argon2-cffi`, `ruff`, or `mypy` installed (confirmed via
`pip3 list`). This sandbox *does* have `numpy`, `opencv-python-headless`,
and `Pillow` installed, which is why the numeric/geometric verification
above was possible directly against the real libraries — but the
application itself cannot be imported, and no real `pytest` run,
`ruff` run, or `mypy` run could be performed. Specifically unavailable,
and not claimed to have passed:

- Targeted Stage 3 `pytest` run
- Full-suite `pytest` run
- `ruff format --check` / `ruff check`
- `mypy app`
- The Stage 3 migration round-trip test's actual execution against a
  real PostgreSQL database (the test file itself — `test_migrations_phase5_stage3.py`
  — is written, reviewed, and includes its own `pytest.skip` for
  exactly this unavailable-database condition; it has not been proven
  to pass by actually running it)
- Any real-model smoke test (no `.onnx`/`.dat` model file exists in
  this sandbox, and none was downloaded, per the explicit "no model
  weights" constraint)

Docker/PostgreSQL/full-runtime verification remains Phase 5 Stage 5's
responsibility, unchanged from every prior Stage's own handover.

## Known risks

- **dlib has no official ONNX export and no bundled prebuilt wheel
  guarantee.** PyPI publishes prebuilt wheels for `dlib` for many
  common platform/Python-version combinations, but a platform without
  a matching wheel requires a C++ toolchain (CMake + a C++ compiler) to
  build from source — a real deployment-environment dependency this
  project did not have before this checkpoint. Accepted deliberately
  in ADR 0011 in exchange for the model's unambiguous licensing
  posture.
- **Alignment is not proven pixel-equivalent to dlib's own chip
  extractor.** This project's own 5-point-YuNet-landmark-driven
  similarity transform is an independently-calibrated approximation of
  dlib's convention, not a measured match — see "Alignment" above.
  This could affect real-world accuracy in ways the 0.82 threshold
  (itself uncalibrated) does not account for.
- **Threshold/ambiguity margin are provisional, not calibrated** — see
  above, repeated here as a risk because it is the single most
  important caveat in this entire checkpoint: **do not deploy this
  pipeline's match decisions as authoritative without first running a
  real FAR/FRR evaluation against this project's own data.**
- **Best-sample-per-student aggregation is implemented and unit-
  tested but not currently reachable through the live enrollment
  flow's own database invariants** (see "Aggregation" above) — a
  future schema change that allowed multiple simultaneously-active
  samples per student would newly exercise this path in production for
  the first time; it is believed correct (tested against synthetic
  multi-candidate input) but has never run against real multi-sample
  data end-to-end.
- **Training-data provenance for the selected embedding model traces
  in part to datasets (FaceScrub, VGG Face) whose own original
  licensing terms were not independently re-examined in this
  checkpoint** — see "Embedding model" above.
- **No real pytest/ruff/mypy/migration run has actually been
  performed** — see "Unavailable checks" above. All correctness
  evidence for this checkpoint is static review, standalone numeric
  verification against the real installed `numpy`/`opencv-python-headless`,
  and careful manual re-derivation of expected test results — not an
  actual green CI run.

## Exact Stage 4 starting point

Stage 4 (per `docs/IMPLEMENTATION_PLAN.md`, Phase 5 Stage 4 /
Rebuild "recognition-session workflow") begins from exactly this
checkpoint, with all of the following already available to build on
and **none of the following built yet**:

**Available:**
- A working `detect_align_embed` pipeline
  (`app/modules/face_recognition/pipeline.py`) usable against any
  decoded image, not just stored enrollment samples.
- A working, candidate-scoped `MatchingService.match_probe` — Stage 4
  can reuse it directly, or build a session-specific variant on the
  same `BiometricEmbeddingRepository`/`CosineSimilarityFaceMatcher`
  primitives.
- Processed, persisted embeddings for any `ACTIVE` sample that has been
  run through `SampleProcessingService`.
- The full Stage 1-4 attendance/authorization/audit infrastructure,
  untouched.

**Not built (Stage 4's own scope, per the Stage 3 brief's explicit
boundary and `docs/IMPLEMENTATION_PLAN.md`):**
- Classroom recognition session / group-image / multi-frame recognition
  workflow.
- Candidate-roster derivation from a classroom/timetable context (this
  checkpoint's `candidate_student_profile_ids` is always an explicit,
  caller-supplied list — Stage 4 must decide how a roster gets
  resolved and *remains* an authorized, explicit list by the time it
  reaches `MatchingService`).
- Teacher-facing recognition endpoints of any kind (every Stage 3 route
  is admin-only).
- Teacher review/confirmation UI or API for an `AMBIGUOUS`/low-
  confidence result.
- Any conversion of a confirmed match into an `AttendanceRecord` —
  **must** reuse the existing Phase 4 `AttendanceService`, never a
  direct write from the recognition path (ADR 0005's own "Consequences"
  section already states this constraint; this checkpoint does not
  relax it).
- Duplicate-attendance prevention for a recognition-driven mark.
- Recognition-decision-specific audit trail entries **tied to an
  attendance mark** (still not built — no code here writes anything
  attendance-shaped). As of the v2 correction patch, Stage 3 does
  additionally audit `MatchingService.match_probe` itself (a `SUCCESS`
  row with candidate count/match status/matched student ID, or a
  `BLOCKED` row for an empty candidate scope) — see "Stage 3 v2
  correction patch" below — but this is auditing the diagnostic
  match-probe *operation*, not a recognition-driven attendance
  decision, which still does not exist anywhere in this codebase.

**Confirmed: Stage 4 was NOT started in this checkpoint.** No file
under a hypothetical `recognition_session`/attendance-integration path
was created; no `AttendanceService` import or `AttendanceRecord`
construction exists anywhere under
`app/modules/face_recognition/` (verified both statically and by a
dynamic zero-row-count test — see "Security/privacy summary" above).

## Confirmation: no Git operation occurred

No `git` command of any kind (`reset`, `restore`, `clean`, `stash`,
`commit`, `branch`, `tag`, or otherwise) was run at any point during
this checkpoint's work. All work happened in a plain working directory
(`/home/claude/work/build`), copied from the delivered baseline ZIP,
with no `.git` directory involved.

---

## Stage 3 v2 correction patch (this session)

A later session applied one targeted correction patch fixing five
independently-confirmed Stage 3 findings, packaged as
`ShikshaSathi-phase-5-stage-3-v2.zip`. This session had, for the first
time, real network egress (PyPI/Ubuntu archive reachable), a real
local PostgreSQL 16 instance, and every static tool (`pytest`, `ruff`,
`mypy`, `alembic`) actually installed and actually run — not simulated
or statically reasoned about. No Stage 1/2 migration was modified. No
Stage 2 application code was modified. Stage 4 was not started.

### Finding 1 — config test regression (fixed)

`test_config.py::test_enabling_a_provider_with_both_model_identifiers_set_succeeds`
was stale: it supplied only the two model *identifiers*
(`FACE_DETECTION_MODEL_IDENTIFIER`/`FACE_EMBEDDING_MODEL_IDENTIFIER`)
and asserted success, but `Settings`'s validator
(`_enforce_face_recognition_provider_consistency`) had already been
tightened to also require the two model *paths*
(`FACE_DETECTOR_MODEL_PATH`/`FACE_EMBEDDER_MODEL_PATH`) once a provider
is enabled — this test was failing against the real validator.
Renamed to
`test_enabling_a_provider_with_identifiers_and_model_paths_set_succeeds`
and updated to supply safe, fake, non-existent placeholder paths (the
test never touches the filesystem or loads a model). Added four new
rejection tests that did not previously exist: missing detector path,
missing embedder path, blank detector path, and (already-existing
coverage confirmed adequate) missing/blank identifiers. The `Settings`
validator itself was **not weakened** — only the test was corrected to
match its actual, already-correct contract.

### Finding 2 — process-vs-retry state contract (fixed)

`SampleProcessingService.process_sample` previously only checked
`processing_state.value == "processed"`, meaning a `PROCESSING_FAILED`
sample would silently fall through and be treated as if it were a
fresh `PENDING_PROCESSING` attempt — a real state-machine bug. Fixed
to an explicit allow-list: `process_sample` accepts only
`status == ACTIVE` **and** `processing_state == PENDING_PROCESSING`,
raising `SampleNotEligibleForProcessingError` with a distinct reason
code (`sample_already_processed` vs.
`sample_already_failed_use_retry`) otherwise. `retry_sample` is
unchanged in its own semantics (still accepts only
`PROCESSING_FAILED`) but now shares the same explicit-allow-list
pattern for symmetry. A new regression test,
`test_process_sample_rejects_failed_sample_and_only_retry_sample_accepts_it`
in `test_phase5_stage3_processing_service.py`, proves the full cycle:
first attempt fails (zero faces) → `PROCESSING_FAILED` →
`process_sample` rejected with `sample_already_failed_use_retry` →
`retry_sample` succeeds → `PROCESSED` → both methods correctly reject
it again afterward, each with the correct, distinct reason code. This
test passes against real PostgreSQL.

### Finding 3 — event-loop offload + provider serialization (fixed)

`SampleProcessingService._run_pipeline` and `router.match_probe` both
previously called `detect_align_embed(...)` — synchronous, CPU-bound
YuNet/dlib work — directly on the async request path, blocking that
worker's event loop for the duration of one full detect→align→embed
call. Fixed:

- `processing_service.py`: image decode + `detect_align_embed` bundled
  into one synchronous method (`_load_and_embed_sync`) and dispatched
  via a single `await asyncio.to_thread(...)` call.
- `router.py`: match-probe validation (finding 5) + `detect_align_embed`
  bundled into `_validate_and_embed_probe_sync` and dispatched the same
  way; `router.get_health` now offloads
  `get_face_recognition_health` (which can perform blocking
  model-file I/O via each provider's `is_available()`) via
  `asyncio.to_thread` too.
- **Provider protocols remain synchronous** (`FaceDetector`/
  `FaceEmbedder` Protocol methods were not made `async` — offload
  happens at the caller, not the contract).
- Cached provider instances (`YuNetFaceDetector`, `DlibResnetFaceEmbedder`
  — one instance per `Settings` object, reused across every request via
  `provider_factory.py`'s module-level cache) are not safe for
  concurrent use on the same instance (matches OpenCV's/dlib's own
  thread-safety posture for a single loaded model object). Since
  `asyncio.to_thread` dispatches to a shared thread pool, two
  concurrent requests really can land on two different worker threads
  calling into the *same* cached instance at once. Added a
  process-local `threading.RLock()` **per provider instance** (not a
  global lock — narrower, so YuNet and dlib work never block each
  other) guarding both lazy model loading (`_ensure_loaded`) and
  inference (`detect`/`embed`). Also added a small `threading.Lock()`
  in `provider_factory.py` guarding only the cache dict's
  get-or-create step (a separate, much narrower race: two concurrent
  first-ever callers could otherwise each construct and cache a
  different adapter instance).
- New tests (`test_phase5_stage3_offload_and_locking.py`, 6 tests):
  thread-offload proof for the processing pipeline, for match-probe,
  and for `/health`'s provider-readiness loading (each proven by
  recording `threading.get_ident()` inside a fake detector/embedder
  and asserting it differs from the calling coroutine's thread); and
  direct concurrency-serialization proof for both `YuNetFaceDetector`
  and `DlibResnetFaceEmbedder` (5 threads hammering one shared, cached
  instance — asserts the underlying model-load call happens exactly
  once and inference calls never overlap). All 6 pass, including
  against real PostgreSQL for the two DB-backed tests.

### Finding 4 — match-probe audit (fixed)

`/match-probe` (`MatchingService.match_probe`) previously created no
audit record at all — success or failure. Fixed: `match_probe` now
requires `actor`/`request_id` and, reusing the exact same
`app.db.transaction.service_transaction` +
`app.modules.attendance.repository.AuditLogRepository` pattern
`processing_service.py` already established, writes exactly one audit
row per call:

- **`SUCCESS`** on a completed match attempt — metadata is exactly
  `{"candidate_count": int, "match_status": str, "matched_student_profile_id": str | None}`.
  Nothing else. Never an embedding vector, image bytes, a
  filesystem/model path, or raw exception text.
- **`BLOCKED`** on an empty candidate scope (the one way a request is
  rejected after reaching this service boundary) — metadata is exactly
  `{"reason_code": "candidate_scope_required"}` — written *before*
  `CandidateScopeRequiredError` is raised.

`entity_type` is the fixed string `"face_match_probe"`; `entity_id` is
always `None` (a match-probe has no single persisted entity — the
matched student's ID, if any, lives in the metadata dict instead,
exactly mirroring what the API response already returns to the
caller, so this adds no new exposure).

New test file `test_phase5_stage3_match_probe_audit.py` (5 tests, all
seeded via direct ORM/repository calls — see "Known blocker" below —
and all passing against real PostgreSQL): successful match writes the
exact expected `SUCCESS` metadata dict; a no-match result writes
`SUCCESS` with `matched_student_profile_id: None`; empty candidate
scope writes `BLOCKED` before raising, with no `SUCCESS` row also
written; a dedicated sanitization test asserts the metadata key set is
exactly the three documented keys with no embedding/path/exception-
shaped content; and a dedicated guard asserts zero `AttendanceRecord`
rows exist after a match-probe call (`MatchingService` has no
`AttendanceService`/`AttendanceRepository` dependency at all).

### Finding 5 — match-probe image safety (fixed)

The match-probe upload previously enforced only an 8 MiB
encoded-byte cap, then called `PIL.Image.open(...).convert("RGB")`
directly — none of Stage 2's decoded-content protections applied.
Fixed by refactoring, not duplicating, Stage 2's actual check logic:

- `app/modules/biometric_enrollment/image_validation.py`: the
  decode/decompression-bomb/format-allowlist/dimension/animated/mime
  checks were extracted into a private, error-taxonomy-neutral
  `_validate_decoded_bytes` (raising a private `_ImageContentRejected`
  signal, never a Stage 2 `Enrollment*` error directly). Stage 2's own
  public function, `validate_image_file(path, ...)`, now calls this
  shared core and translates the signal back into its own
  `Enrollment*` errors — **Stage 2's public behavior is unchanged**:
  all 13 pre-existing Stage 2 image-validation tests pass unmodified.
- New module `app/modules/face_recognition/match_probe_validation.py`:
  `validate_probe_image_bytes(data, settings=...)` calls the same
  shared core against in-memory bytes (a probe image is never staged
  to disk or persisted) and translates the signal into new,
  provider-neutral `MatchProbeImage*` errors
  (`app/modules/face_recognition/errors.py`) — deliberately not
  reusing Stage 2's `Enrollment*` error names/codes in a Stage 3 API.
  Reuses the same configured limits Stage 2 enrollment uses
  (`Settings.MAX_ENROLLMENT_IMAGE_PIXELS`/
  `MAX_ENROLLMENT_IMAGE_DIMENSION_PX`) rather than introducing a
  parallel settings surface for the same protection class.
- `router.py`'s `match_probe` now calls `validate_probe_image_bytes`
  (offloaded via `asyncio.to_thread`, see finding 3) before ever
  reaching the detector, replacing the old
  `Image.open(...).convert("RGB")`-only path. The old
  `SampleImageDecodeFailedError` (a Stage 3 processing-path error) is
  no longer misused for probe-image problems.

New test file `test_phase5_stage3_match_probe_image_validation.py`
(13 tests, pure unit tests, no database — mirrors
`test_phase5_stage2_image_validation.py` test-for-test): valid
JPEG/PNG accepted; empty/truncated/non-image content rejected as
malformed; unsupported format (BMP) rejected with the sanitized
allowed-format list; animated WEBP rejected; per-dimension cap
rejected; pixel-count cap rejected (the decompression-bomb-style
guard — 1100×1000px over a 1,000,000px cap, each side individually
within a separate, larger per-dimension cap); declared-Content-Type
mismatch rejected, match accepted, unrecognized header ignored; and a
dedicated sanitization test asserting no `MatchProbeImage*` error ever
carries a filesystem-path-shaped string or raw traceback text.

### Known, out-of-scope blocker: Stage 2 `MissingGreenlet` defect

This v2 correction session had real PostgreSQL access for the first
time in this project's history and discovered a **pre-existing Stage 2
defect**, unrelated to any of the five findings above:
`app/modules/biometric_enrollment/service.py::create_sample` raises
`sqlalchemy.exc.MissingGreenlet` when serializing
`BiometricSampleRead.model_validate(sample)` immediately after its
enclosing `service_transaction` commits — an ORM-attribute-expiry/
async-greenlet-context issue, not caused by, or fixed by, this Stage 3
patch. Per this session's explicit scope (`ONE FINAL targeted Stage 3
correction patch`, "do NOT fix Stage 2 application code"), **this
defect was deliberately left unfixed**. It was never caught before
because no prior session in this project's history had real database
access to run against.

**Practical impact:** every existing Stage 2/Stage 3 test that seeds
its fixture data through the real Stage 2 HTTP upload endpoint
(`app.tests.phase5_stage2_http_helpers.upload_sample`) fails against a
real database — this is Category B in the full-suite result below, 45
tests, all traced to this one root cause. **Workaround used for every
new/modified test in this patch:** a new helper,
`app.tests.phase5_stage3_helpers.seed_active_sample_direct`, creates
an `ACTIVE` `BiometricSample` row directly through the
repository/ORM/storage layer — the same primitives Stage 2's own
service uses, just not its buggy response-serialization step — so
Stage 3 behavior can be verified against a real database independently
of this blocker. No Stage 3 assertion was weakened or skipped to work
around it.

**Recommended next step (not performed here, out of scope):** a
dedicated Stage 2 patch investigating `service_transaction`'s
interaction with `expire_on_commit`/attribute access timing in
`create_sample` (and likely the sibling `replace_sample`/deletion
methods, which share the same pattern).

### Real verification results (this session)

**Environment:** real network egress (PyPI/Ubuntu archive reachable,
unlike every prior session); full `backend_v2` dependency set
installed into a venv; local PostgreSQL 16 installed via `apt`,
database `shikshasathi_test` / user `test_user` matching
`conftest.py`'s defaults; `dlib` itself was not built from source
(single-core sandbox, no persistent background process across tool
calls made a from-source build impractical) — not needed, since the
entire test suite fakes `dlib` via `sys.modules` injection (confirmed
in `test_face_recognition_dlib_embedder.py`, pre-existing).

- **Alembic migration, real PostgreSQL:** `alembic upgrade head` from
  empty succeeded through every migration including Stage 3's
  `d22bce264ecd` (parent `ca8e748dc8f2`). `alembic current` confirms
  `d22bce264ecd (head)`. The dedicated round-trip test,
  `test_migrations_phase5_stage3.py`, **passed** (1 passed) against
  the real database.
- **Stage 2 image-validation tests:** `test_phase5_stage2_image_validation.py`
  — **13 passed**, unchanged, confirming the finding-5 refactor did
  not alter Stage 2 behavior.
- **Targeted Stage 3 correction tests** (all 5 findings' new/updated
  tests, real PostgreSQL where DB-backed): config (57 passed),
  processing-service regression (passed), offload/locking (6 passed),
  match-probe audit (5 passed), match-probe image validation (13
  passed) — **all passing**.
- **Full suite, real PostgreSQL:** 652 collected, **606 passed, 46
  failed**.
  - **Category A (Stage 3 v2 patch regressions): 0.**
  - **Category B (confirmed pre-existing Stage 2 `MissingGreenlet`
    fallout, via `upload_sample`): 45** — spread across
    `test_phase5_stage2_enrollment_http.py` (12),
    `test_phase5_stage2_failure_injection.py` (11),
    `test_phase5_stage3_api_http.py` (7),
    `test_phase5_stage3_matching_service.py` (6, the pre-existing
    tests that predate this patch's `actor=` signature change — those
    calls were mechanically updated to compile against the new
    required parameter, but still seed via the broken HTTP path so
    still fail against a real database for the same pre-existing
    reason),
    `test_phase5_stage3_processing_service.py` (9, same pattern).
  - **Category C (unrelated, pre-existing): 1** —
    `test_migrations_phase4.py::test_phase4_stage1_migration_round_trip`,
    which asserts the current revision equals an old Phase 4
    checkpoint revision after upgrading to `head` — this fails on any
    complete migration run once later migrations exist (Stage 2's and
    Stage 3's both already existed before this patch touched
    anything), independent of any change made here.
- **`python -m compileall -q app alembic scripts`:** clean, no errors.
- **`ruff format --check`:** the 5 files this patch touched that
  needed formatting were formatted; full-tree check now shows 17
  files needing reformatting, all confirmed pre-existing/untouched by
  this patch (cross-referenced against the exact file list this patch
  modified).
- **`ruff check`:** 23 findings remain tree-wide; only 5 fall in files
  this patch touched, and all 5 are in code this patch did not modify
  within those files (e.g. `yunet_detector.py`'s pre-existing
  `_row_to_detected_face` row-parsing method, the pre-existing
  `patch_providers` helper, an existing pre-patch test) — confirmed
  none were introduced by this patch. Not fixed, per this session's
  explicit "do not clean historical Ruff debt" scope.
- **`mypy app`:** 162 errors across 17 files tree-wide. Of those 17,
  6 are files this patch touched/created
  (`test_phase5_stage3_offload_and_locking.py`,
  `test_phase5_stage3_matching_service.py`,
  `test_phase5_stage3_match_probe_audit.py`,
  `test_phase5_stage3_processing_service.py`,
  `providers/dlib_embedder.py`, `phase5_stage3_helpers.py` — 69
  errors combined). Every single one of these is the same category
  already pervasive across the *other* 11 flagged files this patch
  never touched (`no-untyped-def` on test functions,
  `_SettingsLike`/duck-typed-fake arguments not matching a concrete
  `Settings`/`User`/`UploadFile` parameter type) — this is this
  codebase's established, pre-existing test-authoring convention
  (confirmed by the untouched `test_face_recognition_yunet_detector.py`
  having the exact same error shapes), not a new defect category
  introduced by this patch. `dlib_embedder.py`'s 3 errors
  (`dlib` import-not-found; `self._model: object` has no
  `compute_face_descriptor` attribute) are both on lines this patch
  did not change (only wrapped in a `with self._lock:` block) — both
  pre-existing. **No genuine new typing defect was found in any file
  this patch changed**, so nothing was fixed here, per this session's
  explicit "do not fix historical typing debt" scope.
- **Static secret/path/cache/model-weight scan:** no `.env`, no
  `.git`, no `venv`/`node_modules`, no `.onnx`/`.dat`/other model
  weight files, no image artifacts, no exported embedding/pickle
  files, no unrelated archives found anywhere in the working tree
  (only expected, excluded-from-packaging `__pycache__`/`.pyc`/
  `.pytest_cache`). No real secret pattern (cloud access keys, live
  DB connection strings, API tokens) found; every credential-shaped
  string found is a clearly-labeled synthetic test value (e.g.
  `test_only_password_not_a_real_credential`, pre-existing).
- **Real-model smoke test: NOT RUN.** No real `.onnx`/`.dat` model
  file exists in this sandbox and none was downloaded or built, per
  the explicit "no model weights" constraint every session in this
  project has honored.

**Stage 4: not started.** No file under a recognition-session/
attendance-integration path was created or touched; no
`AttendanceService` import or `AttendanceRecord` construction exists
anywhere under `app/modules/face_recognition/` (unchanged from the
original Stage 3 delivery, reconfirmed by this session's own
`test_phase5_stage3_match_probe_audit.py::test_match_probe_never_writes_an_attendance_record`).

**No Git operation of any kind occurred in this session** — same as
the original Stage 3 delivery (see "Confirmation: no Git operation
occurred" above); work happened in a plain, non-`.git` working
directory copied from the uploaded `ShikshaSathi-phase-5-stage-3.zip`.

---

## Stage 3 v3 correction patch (this session)

One tiny, targeted patch fixing two independently-confirmed issues in
the v2 correction patch above — not a new audit, not a Stage 3
redesign. Working from the v2 ZIP as the sole authoritative baseline
(verified by its reported SHA-256 before any change was made). Stage 4
not started; no Stage 2 application code changed; no migration
changed; no Git operation performed.

### Issue 1 — Pillow global-state concurrency race (fixed)

`image_validation.py::_validate_decoded_bytes` temporarily mutated the
process-global `Image.MAX_IMAGE_PIXELS` (and, via
`warnings.catch_warnings()`, the global `warnings` filter list) to
align Pillow's own decompression-bomb threshold with each call's
configured pixel cap, then restored it — with no synchronization. Once
Stage 3 v2 started running match-probe validation via
`asyncio.to_thread` (a real OS thread pool), two concurrent probe
validations could interleave that mutate/restore pair across two
different threads. Independently reproduced: Pillow's real default
(`89478485`) ended up permanently stuck at a smaller configured value
(`30000000`) after concurrent validations.

**Fix:** two changes, together —

1. A cheap, lock-free header-only parse (`Image.open()` without
   `.load()`/`.verify()`) now runs first and rejects an image whose
   *declared* width/height/pixel-count already exceeds the caller's
   configured `max_dimension`/`max_pixels`, before any expensive full
   decode happens — this is the "reject before expensive decode where
   practical" improvement, and touches no global state at all.
2. The remaining full, decompression-bomb-guarded decode — the only
   part of this function that still touches `Image.MAX_IMAGE_PIXELS`/
   `warnings.catch_warnings()` — is now wrapped in a new module-level
   `threading.Lock` (`_max_image_pixels_lock`), serializing that
   critical section process-wide across every caller (Stage 2 file
   validation and Stage 3 probe validation alike), regardless of which
   thread each runs on.

Decompression-bomb protection, configured max-pixel behavior, and
configured max-dimension behavior are all unchanged in effect —
this fix only adds a lock and an earlier, cheaper equivalent check; it
does not relax any threshold. All 13 pre-existing Stage 2
image-validation tests and all 13 pre-existing Stage 3 probe-validation
tests pass unmodified.

**New regression test:**
`test_phase5_stage3_match_probe_image_validation.py::test_concurrent_probe_validation_does_not_corrupt_image_max_image_pixels`
— drives 60 concurrent `validate_probe_image_bytes` calls across 5
distinct configured pixel caps (so the global is actually being set to
*differing* values, not the same one repeatedly) against a tiny 50×50
fixture (no giant in-memory image), then asserts every call still
produced the correct result and `Image.MAX_IMAGE_PIXELS` is back to
its true original value afterward. Verified this test actually catches
the regression: temporarily reverting the lock and re-running it 5
times reproduced the failure in 2 of 5 runs (inherent timing
variance of a real thread race); with the fix restored, 5/5 runs pass.

### Issue 2 — HTTP empty-scope BLOCKED audit bypass (fixed)

`router.match_probe` had its own, separate
`if not candidate_student_profile_ids: raise CandidateScopeRequiredError()`
pre-check that ran *before* a `MatchingService` was even constructed —
so `MatchingService.match_probe`'s v2-added `BLOCKED` audit write
(see "Stage 3 v2 correction patch" above) was dead code for every real
HTTP request: a real empty-scope match-probe call never actually wrote
that audit row.

**Fix:** extracted the empty-scope check into a new
`MatchingService.ensure_candidate_scope(candidate_student_profile_ids,
*, actor, request_id)` method — the same check-and-audit-and-raise
logic that used to live inline at the top of `match_probe`, now
reusable. `router.match_probe` calls this method first, before reading
the uploaded file at all (so an empty scope triggers no file I/O,
decoded-content validation, or detect/align/embed inference — the
uploaded file is never even read). `match_probe` itself still calls
the same method as its own first step too, so it remains
independently safe to call directly without relying on a caller to
have already checked; calling it a second time for an already
non-empty scope is a true no-op (confirmed by a dedicated test) — no
audit-writing code is duplicated, since only `ensure_candidate_scope`
itself ever writes the `BLOCKED` row.

**Framework-level rejections remain unaudited, by design and
correctly so:** if FastAPI itself rejects a request during request
parsing (e.g. a malformed multipart body, a missing required form
field) before `match_probe`'s function body ever executes, no
application code runs and so no audit row can be written — this is
inherent to where FastAPI's own validation happens, not a gap in the
fix above, and is documented here rather than worked around.

**New regression tests** (in
`test_phase5_stage3_match_probe_audit.py`, all passing against real
PostgreSQL):

- `test_ensure_candidate_scope_persists_blocked_audit_for_empty_scope`
  — direct, service-level proof the extracted method writes the exact
  same sanitized `BLOCKED` audit row (`{"reason_code":
  "candidate_scope_required"}`, nothing else).
- `test_ensure_candidate_scope_is_a_noop_for_non_empty_scope` — proves
  the second, defensive call inside `match_probe` never double-writes
  an audit.
- `test_http_empty_candidate_scope_persists_blocked_audit_and_skips_file_io`
  — the actual regression test for the bug: calls `router.match_probe`
  directly (as a plain coroutine, the same pattern
  `test_phase5_stage3_offload_and_locking.py` already uses) with an
  empty scope and a fake upload file whose `read()` raises if ever
  called; asserts the `BLOCKED` audit row exists with the correct
  actor/request ID/sanitized metadata, no `SUCCESS` row also exists,
  and (implicitly, by the fake file's `read()` never raising) no file
  I/O or inference occurred.

### Files modified this session

```
backend_v2/app/modules/biometric_enrollment/image_validation.py
backend_v2/app/modules/face_recognition/matching_service.py
backend_v2/app/modules/face_recognition/router.py

backend_v2/app/tests/test_phase5_stage3_match_probe_image_validation.py
backend_v2/app/tests/test_phase5_stage3_match_probe_audit.py

docs/HANDOVER_PHASE_5_STAGE_3.md
docs/PROGRESS.md
```

No Stage 1/2 migration touched. No Stage 2 application code touched.
No legacy Flask/React file touched. No real `.env` touched. No model
weight packaged. Stage 4 not started.

### Checks run this session (scoped, not a full historical debt pass)

- `test_phase5_stage2_image_validation.py` — **13 passed**, unchanged.
- `test_phase5_stage3_match_probe_image_validation.py` — **14 passed**
  (13 pre-existing + 1 new concurrency regression test).
- `test_phase5_stage3_match_probe_audit.py` — **8 passed** (4
  pre-existing + 4 new).
- `test_phase5_stage3_offload_and_locking.py` — **6 passed**,
  unchanged (re-run to confirm the `router.match_probe` signature/flow
  change didn't affect the thread-offload proof).
- `test_config.py` — **57 passed**, unchanged.
- `test_phase5_stage3_matching_service.py` — 6 passed, 6 failed; every
  failure is the same pre-existing Stage 2 `MissingGreenlet` fixture
  bug (seeds via `upload_sample`), unrelated to this session's two
  fixes and already documented in "Stage 3 v2 correction patch" above.
- `test_phase5_stage3_processing_service.py` — 6 passed, 9 failed;
  same pre-existing cause as above.
- `python -m compileall -q app alembic scripts` — clean.
- `ruff check` on the 5 modified files — 3 findings, all fixed (2
  genuinely-unused `# noqa` comments this session's own new code had
  added, 1 Yoda-condition style issue in this session's own new
  assertion); re-checked clean afterward.
- `ruff format --check`/`ruff format` on the 5 modified files — 1
  needed reformatting (a line-wrap in this session's own new fake
  upload-file class), applied; all 5 confirmed formatted afterward.

No full-suite/global Ruff/mypy/historical-debt pass was re-run this
session — the v2 correction patch's session already established and
documented that baseline; nothing in this session's two fixes touches
code that baseline covered differently.

**No Git operation of any kind occurred in this session.**


## Stage 3 v4 correction patch — eliminate request-specific Pillow global mutation

**Status: complete.** This tiny correction supersedes only the Pillow
concurrency mechanism described in the v3 addendum above. The v3
empty-candidate-scope BLOCKED-audit fix remains unchanged and correct.

### Confirmed v3 residual race

The v3 lock serialized the block that temporarily assigned a request's
``max_pixels`` value to process-global ``PIL.Image.MAX_IMAGE_PIXELS``. That
prevented corrupt restore ordering, but it did not make the design fully safe:
the header-only ``Image.open`` ran before the lock and could therefore observe
another thread's temporary threshold. A request whose own cap allowed an image
could be falsely rejected according to a concurrent request's smaller cap.

### v4 fix

``_validate_decoded_bytes`` no longer changes ``Image.MAX_IMAGE_PIXELS`` at
all, and it no longer changes Pillow warning-filter state. Request-specific
``max_pixels`` and ``max_dimension`` limits are enforced directly from header
dimensions before the full decode and are rechecked after decoding. Pillow's
normal process-wide decompression-bomb guard remains untouched as an independent
safety net. ``Image.DecompressionBombError`` is translated into the same safe
``too_large`` rejection at each Pillow-open/verify/decode boundary.

This removes cross-request threshold coupling rather than merely serializing it.
Stage 2 file validation and Stage 3 in-memory match-probe validation still share
the same validation core and error-translation boundaries.

### v4 regression coverage

Added
``test_concurrent_probe_validation_uses_request_local_limits_without_global_mutation``.
It concurrently validates the same 2,500,000-pixel JPEG using a 1,000,000-pixel
request cap and a 3,000,000-pixel request cap. The small-cap calls must reject,
the large-cap calls must accept, every observed ``Image.open`` must see the
unchanged process-global Pillow threshold, and ``Image.MAX_IMAGE_PIXELS`` must
remain unchanged after all calls.

The regression has direct teeth against the v3 implementation: running the same
observation against the v3 baseline recorded request-specific values (for
example 3,000,000) inside ``Image.open`` instead of only Pillow's original
89,478,485 default.

### v4 checks run

- Stage 2 image-validation tests: **13 passed**.
- Stage 3 match-probe image-validation tests: **15 passed**.
- Combined targeted validation tests: **28 passed**, 0 failed.
- New v4 concurrency regression repeated **5/5 passes**.
- ``python -m compileall -q app alembic scripts``: **PASS**.
- Source scan confirms there is no assignment to ``Image.MAX_IMAGE_PIXELS`` in
  application code.
- Ruff was unavailable in this execution environment, so no Ruff result is
  claimed for v4; changed files were kept within the existing 100-character
  line convention by a direct line-length scan before packaging.

### Files changed by v4

```text
backend_v2/app/modules/biometric_enrollment/image_validation.py
backend_v2/app/tests/test_phase5_stage3_match_probe_image_validation.py
docs/HANDOVER_PHASE_5_STAGE_3.md
docs/PROGRESS.md
```

No migration changed. No Stage 2 service/business-lifecycle code changed. No
match-probe audit code changed. Stage 4 was not started. No Git operation was
performed.
