# ADR 0011: Phase 5 Stage 3 — embedding model, matching metric, and thresholds

## Status

**Accepted** (Rebuild Phase 5, Stage 3). This ADR resolves the two items
ADR 0005 explicitly deferred to Stage 2/3 under "What is decided vs.
deferred": the face **embedding** model, and the initial
`FACE_MATCH_THRESHOLD` / `FACE_MATCH_AMBIGUOUS_MARGIN` values. ADR 0005
itself is unmodified — its architecture decision (server-side local
inference, YuNet detector, the `detect`/`embed`/`match` Protocol
boundary) stands as-is and is not revisited here.

## Context

ADR 0005 accepted YuNet (MIT-licensed, confirmed) as the detector but
left the embedding model an open, licensing-blocked item: the model
most commonly paired with YuNet in OpenCV's own tutorials, SFace, has
an unresolved upstream licensing question (ADR 0005, "Licensing: what
is actually confirmed, and what is an open blocker") and remains
unselected. Stage 3 must resolve this before any model weight is
referenced, per ADR 0005's own instruction: either independently verify
SFace's provenance and redistribution rights, or select a differently,
unambiguously licensed alternative.

## Alternatives compared

Per ADR 0005's carried-forward evaluation criteria (licensing first,
as a hard gate; then accuracy/benchmark context, maintenance,
dimension, CPU viability, ONNX availability, model size,
interoperability with the chosen YuNet+alignment pipeline):

### 1. SFace (`opencv_zoo/models/face_recognition_sface`) — still not selected

No new evidence changes ADR 0005's finding. SFace remains blocked on
the same unresolved licensing question; this ADR did not attempt to
independently re-resolve it, since alternative 3 below resolves the
blocker without needing to.

### 2. InsightFace / ArcFace family (e.g. the `buffalo_l` model pack) — rejected, license

Compared newly in this ADR. InsightFace's own published model zoo
states its models, including `buffalo_l`, are made available for
**non-commercial research purposes only**. That is a clear,
unambiguous restriction — not a licensing question left open the way
SFace's is, but an explicit term this project (a school attendance
system with no stated non-commercial-research carve-out) cannot rely
on. Rejected on the same "license must be unambiguous, not merely
popular" ground ADR 0005 already established for SFace.

### 3. dlib's `dlib_face_recognition_resnet_model_v1` — selected

**Evidence gathered for this decision (cited precisely, not
paraphrased into a stronger claim than the sources support):**

- **The dlib software library** (the Python/C++ package this project
  now depends on to *run* the model — `app/modules/face_recognition/providers/dlib_embedder.py`)
  is licensed under the **Boost Software License 1.0** — a permissive
  license explicitly allowing use "however you like, even in closed
  source commercial software" (dlib's own `dlib/LICENSE.txt`, mirrored
  on PyPI's project page and the GitHub repository README).
- **The model file itself is a separate artifact with its own,
  separately-stated terms** — this distinction matters and is kept
  explicit throughout this ADR and the Stage 3 handover:
  `dlib_face_recognition_resnet_model_v1.dat`, published at
  `http://dlib.net/files/dlib_face_recognition_resnet_model_v1.dat.bz2`
  (mirrored at `github.com/davisking/dlib-models`). Its creator and
  dlib's maintainer, Davis King, states directly (dlib's own
  `dnn_face_recognition_ex.cpp` example, and a Feb 2017 post on
  `blog.dlib.net`): "Just like all the other example dlib models, the
  pretrained model used by this example program is in the public
  domain. So you can use it for anything you want." The
  `dlib-models` repository's own README repeats this in the
  maintainer's own words: "anyone can do whatever they want with these
  model files as I've released them into the public domain."
- **Strength of this evidence, stated honestly:** this is a direct,
  repeated, unambiguous statement from the model's own author/
  maintainer — the most authoritative source available short of a
  bundled machine-readable `LICENSE` file shipped alongside the `.dat`
  artifact itself (no such file is bundled with the weight file; the
  statement lives in the surrounding example-program comments and the
  maintainer's blog, not in a `SPDX-License-Identifier` header on the
  artifact). This ADR treats that as sufficient to select the model
  (a direct authorial public-domain dedication, repeated consistently
  across multiple of the author's own publications over several
  years) while still recording the distinction plainly:  **a
  first-party authorial statement is not formally identical to a
  bundled `LICENSE` file**, and a strict compliance review before a
  wide-scale commercial redistribution of the trained weight file
  itself (as opposed to using it, which this project does) may wish to
  seek an explicit, dated confirmation directly from the maintainer.
  This project **uses** the model for local inference; it does not
  redistribute the `.dat` file itself (see "Model distribution
  strategy" in `docs/HANDOVER_PHASE_5_STAGE_3.md` — the file is never
  committed to this repository or packaged in any ZIP built from it).
- **Training-data provenance — a distinct question from the weight
  file's own stated license, and disclosed rather than glossed over:**
  the model was trained "from scratch on a dataset of about 3 million
  faces...derived from a number of datasets" including the FaceScrub
  dataset and the VGG (VGG Face) dataset, plus images the author states
  he personally collected and cleaned (`blog.dlib.net`,
  `dlib-models` README). FaceScrub and VGG Face are themselves
  research-oriented face datasets with their own historical
  collection/usage terms, distinct from — and not fully resolved by —
  the model author's public-domain statement about the resulting
  trained weights. This ADR does not attempt to independently resolve
  the upstream datasets' own terms; it records this as a known,
  disclosed provenance nuance (see "Known risks" in the Stage 3
  handover) rather than treating the model's public-domain statement as
  automatically settling every question about how the weights came to
  exist.
- **Descriptor dimension:** 128-D, confirmed by the model's own
  documented purpose ("this network is trained in a way that generates
  a 128-dimensional (128D) descriptor") and independently by dlib's own
  example programs (`face_recognition.py`, `dnn_face_recognition_ex.cpp`).
- **Architecture:** a ResNet variant with 29 convolutional layers —
  "essentially a version of the ResNet-34 network...with a few layers
  removed and the number of filters per layer reduced by half"
  (`blog.dlib.net`).
- **Published benchmark context (not this project's own measured
  accuracy — see "Accuracy: explicitly not claimed" below):** 99.38% on
  the standard LFW (Labeled Faces in the Wild) benchmark, as published
  by the model's author. This is the same category of citation ADR
  0005 already made for YuNet's WIDER Face numbers — a third-party
  academic benchmark, not a claim about this project's own classroom
  conditions.
- **No official ONNX export.** dlib ships its own native `.dat` weight
  format and its own inference engine (the `dlib` Python package);
  there is no ONNX Runtime path for this specific model. This is a
  real, accepted trade-off against ADR 0005's stated preference to add
  `onnxruntime` "only if genuinely needed" — see "Consequences" below.
- **CPU viability:** yes — dlib's CNN inference runs on CPU without a
  GPU requirement (matching `Settings.FACE_INFERENCE_DEVICE`'s `"cpu"`
  default).
- **Model size:** ~21.4 MB (per the cited O'Reilly/*Mastering OpenCV 4*
  reference to the same `.dat` file), reasonable for a free-tier
  deployment's disk/memory budget.
- **Interoperability with the chosen YuNet+alignment pipeline:** dlib's
  own convention (`get_face_chip`) expects a ~150x150 aligned RGB crop;
  Stage 3's own alignment module (`app/modules/face_recognition/alignment.py`)
  produces exactly that shape from YuNet's 5-point landmarks, though
  independently implemented (not calling dlib's own chip extractor,
  which expects dlib's own shape-predictor landmarks) — see that
  module's docstring for the calibration caveat this implies.
- **Maintenance:** dlib is an actively maintained, long-running,
  widely-used project (initial release 2002, stable releases ongoing);
  this specific model file has been dlib's standard face-recognition
  example model since 2017 with no indication of deprecation.

## Decision

**`dlib_face_recognition_resnet_model_v1` (128-D) is selected as the
Stage 3 embedding model**, loaded via the `dlib` Python package behind
the `FaceEmbedder` Protocol
(`app/modules/face_recognition/providers/dlib_embedder.py`). SFace
remains unselected (licensing still unresolved, unchanged from ADR
0005). InsightFace/ArcFace (`buffalo_l` and the same family) is
rejected on explicit non-commercial-research-only licensing terms.

### Similarity metric: L2-normalized cosine similarity

This codebase's domain contract (`app/modules/face_recognition/domain.py`,
Stage 1) fixes cosine similarity as the *only* metric this application
ever computes or stores — never a raw distance. dlib's own official
guidance instead recommends comparing raw 128-D descriptors by
**Euclidean distance**, calling two descriptors the same person if
their distance is below approximately 0.6. Rather than introduce a
second, competing distance-based code path, the Stage 3 embedder
**L2-normalizes every embedding to a unit vector before returning it**
(`DlibResnetFaceEmbedder._l2_normalize`). For unit vectors, cosine
similarity and Euclidean distance carry the same ranking information:

```
cosine_similarity = 1 - (euclidean_distance^2 / 2)
```

This identity is only valid *because* both vectors being compared are
unit-normalized — it is not a general identity between the two
metrics, and the Stage 3 embedder's L2-normalization step is what makes
using it appropriate here. This decision is what let
`app/modules/face_recognition/providers/similarity_matcher.py` use a
single, consistent cosine-similarity computation for every candidate.

### Threshold: a provisional structural default, not a calibrated value

Applying dlib's own 0.6 Euclidean-distance reference through the
identity above:

```
cosine = 1 - (0.6^2 / 2) = 1 - 0.18 = 0.82
```

`Settings.FACE_MATCH_THRESHOLD` is therefore set to **`0.82`**. This is
a **provisional, structural default derived by mathematical translation
of the model author's general-purpose guidance** — it is **not** a
threshold calibrated against this project's own students, cameras, or
classroom conditions, and must not be read as one. No FAR/FRR
evaluation against this project's own data has been run.
**Classroom calibration remains explicitly pending** — see
`app/modules/face_recognition/evaluation.py` (the harness that would
perform it once real, labeled evaluation data exists) and
`docs/HANDOVER_PHASE_5_STAGE_3.md`, "Calibration status: pending."

`Settings.FACE_MATCH_AMBIGUOUS_MARGIN` remains `0.05` (ADR 0005's
Stage 1 placeholder, carried forward unchanged) — also provisional, not
calibrated.

### Multi-sample aggregation: best sample per student

Documented fully in `app/modules/face_recognition/providers/similarity_matcher.py`'s
own module docstring; summarized here as part of this ADR's record of
matching-semantics decisions: when more than one of a student's
enrolled samples is offered as a candidate, the matcher uses the
**maximum** similarity among that student's candidates ("best sample"),
not a mean. Chosen for standard 1:N gallery-matching convention, to
avoid one poor-quality older sample dragging down an otherwise strong
match, and because it needs no additional configuration.

## Consequences

- **Dependencies added in Stage 3:** `opencv-python-headless` (YuNet
  detection, ADR 0005's already-accepted choice, added now that real
  detector code exists), `numpy` (the array representation every
  Stage 3 adapter converts pixel bytes to/from), and `dlib` (this
  ADR's embedding model). **`onnxruntime` is deliberately NOT added** —
  neither YuNet (OpenCV's own DNN module parses the `.onnx` file
  directly) nor dlib (native inference engine) needs it.
- **A real, accepted trade-off against ADR 0005's dependency
  preference:** dlib has no official ONNX export and requires the
  `dlib` Python package's own native inference engine, not
  `onnxruntime`. dlib publishes prebuilt wheels for common platforms/
  Python versions on PyPI; a platform without a matching prebuilt wheel
  would require a C++ toolchain (CMake + a C++ compiler) to build dlib
  from source. This is recorded as a known deployment risk (see the
  Stage 3 handover's "Known risks"), accepted in exchange for an
  unambiguous, direct-from-author public-domain statement on the model
  weight — treated as the harder constraint per ADR 0005's own
  "licensing is a hard gate" framing.
- **No model weight is downloaded, vendored, or committed anywhere in
  this checkpoint.** `Settings.FACE_EMBEDDER_MODEL_PATH` (and
  `FACE_DETECTOR_MODEL_PATH`) are deployer-supplied filesystem paths to
  files obtained independently, outside Git — see
  `app/modules/face_recognition/model_artifacts.py` and the Stage 3
  handover's "Model distribution strategy". Both accept an optional
  SHA-256 for integrity verification.
- **Effective threshold semantics differ from dlib's own official
  guidance.** dlib's documentation describes its 0.6 figure as a
  Euclidean-distance cutoff on raw descriptors; this project never
  computes that raw distance anywhere (embeddings are stored and
  compared only in their L2-normalized, cosine-similarity form) — the
  0.82 figure is this project's own translation, not a value dlib's
  documentation states directly. Anyone recalibrating this threshold
  later must recalibrate the 0.82 cosine value directly, not attempt to
  reason from dlib's 0.6 distance figure a second time.
- **Accuracy: explicitly not claimed**, matching ADR 0005's own
  standard. The 99.38% LFW figure cited above describes the model's
  published academic-benchmark performance, not this project's actual
  classroom accuracy. Real accuracy against this project's own data can
  only be established once Stage 5 (or a later evaluation effort) runs
  `app/modules/face_recognition/evaluation.py` against real, labeled
  evaluation pairs — none of which exist in this repository, per
  `docs/BIOMETRIC_DATA_POLICY.md`'s prohibition on committing real
  student biometric data.
- Phase 5 Stage 4 (recognition-session workflow, converting a confirmed
  match into attendance) may now begin in a future session, since
  neither the embedding model nor the matching metric remain open
  blockers — but Stage 4 is explicitly **not** started in this
  checkpoint.
