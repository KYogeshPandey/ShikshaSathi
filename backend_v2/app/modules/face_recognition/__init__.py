"""Face recognition module (Rebuild Phase 5, Stages 1-4).

Stages 1-3 provide provider-neutral contracts, secure enrollment integration,
and the candidate-scoped detect/align/embed/match pipeline. Stage 4 adds the
authorized recognition-attendance attempt and explicit confirmation lifecycle.
Attendance writes cross the module boundary only through Phase 4's
``AttendanceService``; images and embeddings are never returned by these APIs.

Phase 5 is planned in five stages (``docs/IMPLEMENTATION_PLAN.md``
Phase 5):

- **Stage 1**: provider decision (ADR 0005, now
  Accepted) and this biometric foundation — contracts, protocols,
  errors, configuration, and the biometric data policy
  (``docs/BIOMETRIC_DATA_POLICY.md``). No inference, no enrollment.
- **Stage 2**: face enrollment and secure photo ingestion.
- **Stage 3**: detection, embedding, and matching pipeline — the first
  point at which a real ``FaceDetector``/``FaceEmbedder``/``FaceMatcher``
  implementation is written, and the first point at which
  ``opencv-python-headless`` becomes a real dependency (see ADR 0005's
  "Consequences"). ``onnxruntime`` is a further-deferred decision, added
  only if a selected embedding-model adapter genuinely needs it — the
  YuNet detector itself runs through OpenCV's own DNN module and does
  not require it.
- **Stage 4** (complete): recognition attendance workflow and APIs — a router in
  this module, reusing the Phase 4 ``AttendanceService`` for any actual
  attendance write (a recognition match never writes attendance
  directly; see ``docs/BIOMETRIC_DATA_POLICY.md``).
- **Stage 5**: runtime verification, hardening, and Phase 5 closure.

Stage 5 remains the separate runtime-closure checkpoint and is not started here.
"""
