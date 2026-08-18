"""Phase 5 Stage 2: secure biometric enrollment and photo ingestion.

This module owns everything needed to safely accept, store, replace, and
delete a student's biometric *sample* (an uploaded photo, or a photo
extracted from a validated bulk ZIP) on the student's biometric
*enrollment* record. It deliberately stops there.

No face is ever detected, aligned, or embedded here, and no image byte
is ever returned by any API in this module. That work belongs to Stage 3
(see app/modules/face_recognition/ — Stage 1's provider-neutral
contracts, still unimplemented) and is out of scope by design (see
docs/adr/0005-face-recognition-provider-pending.md and
docs/HANDOVER_PHASE_5_STAGE_2.md's "Stage 3 starting point").
"""
