"""Face crop, alignment, and normalization — Phase 5 Stage 3.

Sits between detection and embedding as its own explicit pipeline stage
(Stage 3 brief, instruction 3: "Do not bury alignment behavior
invisibly inside business services"). Nothing here is provider-specific
in the OpenCV/dlib sense — this module only consumes the already-typed
``DetectedFace``/``DecodedImage`` domain objects and produces a
``NormalizedFaceInput`` — but it does depend on ``numpy`` and OpenCV's
pure-math ``cv2.warpAffine``/``cv2.invertAffineTransform`` (geometric
warp only, no model file, no DNN module) to perform the actual pixel
resampling; conceptually this is still just "crop/rotate/scale math",
not a machine-learning inference step.

**Exact behavior (Stage 3 brief, instruction 3 — documented, not left
implicit):**

- **Input requirement:** the ``DetectedFace`` passed in must carry
  exactly 5 landmarks, in YuNet's own published order — right eye, left
  eye, nose tip, right mouth corner, left mouth corner (pixel
  coordinates in the *source image's* coordinate space, matching
  ``app.modules.face_recognition.providers.yunet_detector``'s output).
  Missing landmarks -> ``FaceLandmarksUnavailableError``. Wrong count
  -> ``FaceLandmarksUnavailableError``.
- **Alignment method:** a similarity transform (uniform scale +
  rotation + translation — 4 degrees of freedom, no shear/perspective)
  estimated via least-squares (``cv2.estimateAffinePartial2D``) mapping
  the 5 detected landmarks onto 5 fixed reference positions within a
  ``150x150`` output canvas. 150x150 is chosen to match dlib's own
  ``get_face_chip`` output convention, since the Stage 3 embedder is a
  dlib ResNet model most commonly exercised against exactly that chip
  shape — see ``docs/HANDOVER_PHASE_5_STAGE_3.md``. The specific
  reference-point layout below is this project's own, independently
  chosen for a 5-point YuNet landmark set; it is **not** guaranteed
  pixel-identical to dlib's own proprietary chip extractor (which
  aligns from dlib's own 5/68-point shape predictor, not YuNet's).
  This is documented explicitly as a **structural default, not a
  calibrated value** — see "Calibration status" in the handover doc.
- **Degenerate geometry:** if the estimated transform is singular (e.g.
  the two eye landmarks coincide, giving no baseline for scale/
  rotation), ``cv2.estimateAffinePartial2D`` returns ``None`` and this
  module raises ``FaceAlignmentFailedError`` rather than propagating a
  cryptic numeric error.
- **Crop padding / clipping at image edges:** alignment warps directly
  from the *whole* source image into the 150x150 output canvas in one
  affine step (no separate crop-then-pad step) — pixels that would fall
  outside the source image's bounds are filled with solid black
  (``cv2.BORDER_CONSTANT``, value ``0``) rather than raising an error or
  wrapping/mirroring source content. A face whose landmarks sit near
  the source image's edge therefore produces a chip with a black
  margin, not a crash — this is a deliberate, safe, and cheap choice
  matching how the same class of edge case is already handled
  elsewhere in this codebase's file/image pipelines (fail-safe over
  fail-loud only for out-of-frame *pixels*, not for missing/invalid
  *landmarks*, which still raise).
- **Eye/nose/mouth landmark handling:** all 5 landmarks participate in
  the least-squares fit (not just the 2 eyes) — this generally makes
  the estimate more robust to a single noisy landmark than a classic
  2-point eye-only similarity transform would be.
- **RGB/BGR handling:** alignment is color-format-agnostic. The output
  ``NormalizedFaceInput.color_format`` is always set to match the input
  ``DecodedImage.color_format`` exactly — no implicit conversion. (The
  Stage 3 embedder adapter, which needs RGB specifically, converts at
  its own boundary via ``app.modules.face_recognition.image_codec.to_rgb``.)
- **Normalization:** pixel values are NOT rescaled/mean-subtracted here
  — the output remains ``uint8`` in ``[0, 255]``, matching
  ``NormalizedFaceInput``'s own contract (opaque ``bytes``). Any
  embedding-model-specific numeric normalization (e.g. dlib's internal
  preprocessing) happens inside that embedder adapter, not here — this
  keeps alignment reusable for a hypothetical future, differently-
  normalized embedder without duplicating this geometric logic.
- **Output dimensions:** always exactly ``ALIGNED_FACE_SIZE_PX x
  ALIGNED_FACE_SIZE_PX`` (150x150), regardless of the source face's
  original size in the image — this is a fixed contract, not a
  configuration value (the embedding model this project selected has a
  fixed expected input geometry; making this a runtime setting would
  imply a flexibility the model itself does not have).
"""

from __future__ import annotations

import cv2
import numpy as np

from app.modules.face_recognition.domain import DecodedImage, DetectedFace, NormalizedFaceInput
from app.modules.face_recognition.errors import (
    FaceAlignmentFailedError,
    FaceLandmarksUnavailableError,
)
from app.modules.face_recognition.image_codec import (
    decoded_image_to_ndarray,
    ndarray_to_normalized_face_input,
)

#: Fixed output chip size — see module docstring, "Output dimensions".
ALIGNED_FACE_SIZE_PX = 150

#: YuNet's own published 5-point landmark order — see
#: ``app.modules.face_recognition.providers.yunet_detector``.
_EXPECTED_LANDMARK_COUNT = 5

# Canonical reference positions within the 150x150 output chip that the
# 5 detected landmarks are mapped onto. See module docstring's
# "Alignment method" for the calibration caveat. Order MUST match
# YuNet's landmark order exactly: right eye, left eye, nose tip, right
# mouth corner, left mouth corner.
_REF_RIGHT_EYE = (54.0, 58.0)
_REF_LEFT_EYE = (96.0, 58.0)
_REF_NOSE_TIP = (75.0, 88.0)
_REF_MOUTH_RIGHT = (60.0, 118.0)
_REF_MOUTH_LEFT = (90.0, 118.0)

_REFERENCE_POINTS = np.array(
    [_REF_RIGHT_EYE, _REF_LEFT_EYE, _REF_NOSE_TIP, _REF_MOUTH_RIGHT, _REF_MOUTH_LEFT],
    dtype=np.float32,
)


def align_face(image: DecodedImage, face: DetectedFace) -> NormalizedFaceInput:
    """Crop, align, and normalize ``face`` (detected within ``image``).

    Raises ``FaceLandmarksUnavailableError`` if ``face.landmarks`` is
    missing or not exactly 5 points, and ``FaceAlignmentFailedError``
    if the landmark geometry is too degenerate to estimate a transform
    from. Never raises any other exception type for bad input — any
    unexpected OpenCV failure is also mapped to
    ``FaceAlignmentFailedError`` (see the ``except Exception`` at the
    bottom, deliberately broad here since this is the last line of
    defense before an alignment failure would otherwise surface as a
    raw, provider-specific error to a caller that only expects this
    module's own two typed errors).
    """

    if face.landmarks is None or len(face.landmarks) != _EXPECTED_LANDMARK_COUNT:
        raise FaceLandmarksUnavailableError()

    source_points = np.array(
        [(point.x_px, point.y_px) for point in face.landmarks], dtype=np.float32
    )

    transform, _inliers = cv2.estimateAffinePartial2D(
        source_points, _REFERENCE_POINTS, method=cv2.LMEDS
    )
    if transform is None:
        raise FaceAlignmentFailedError()

    try:
        source_array = decoded_image_to_ndarray(image)
        aligned = cv2.warpAffine(
            source_array,
            transform,
            (ALIGNED_FACE_SIZE_PX, ALIGNED_FACE_SIZE_PX),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
    except cv2.error as exc:
        raise FaceAlignmentFailedError() from exc

    if aligned.shape != (ALIGNED_FACE_SIZE_PX, ALIGNED_FACE_SIZE_PX, 3):
        # Defensive: warpAffine's dsize argument makes this
        # unreachable in practice, but a shape assumption this module's
        # own contract depends on is worth asserting explicitly rather
        # than silently trusting OpenCV's behavior across versions.
        raise FaceAlignmentFailedError()

    return ndarray_to_normalized_face_input(
        np.ascontiguousarray(aligned), color_format=image.color_format
    )
