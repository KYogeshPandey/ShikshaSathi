"""Role-linked profile data (``TeacherProfile``, ``StudentProfile``).

Deliberately a separate module from ``app.modules.users`` — Phase 2's
``User`` model (email, password hash, role, active flag) stays exactly as
delivered and verified; this module only ever *references* ``users.id``
by foreign key and never duplicates credential/identity fields (Stage 1
brief, instruction A: "email, password, role, authentication, and
refresh-token logic must remain owned by the existing User/auth
modules"). Kept as its own module rather than folded into
``app.modules.users`` so Phase 2's verified files are not touched at all
in Phase 3 — see docs/HANDOVER_PHASE_3_STAGE_1.md for the explicit
rationale.
"""
