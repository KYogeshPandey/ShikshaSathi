"""Attendance core and audit-trail module (Rebuild Phase 4).

Stage 1 delivered the relational foundation: ORM models
(``AttendanceRecord``, ``AuditLog``), stable domain errors, Pydantic
schemas, and repositories. Stage 2 adds the service layer
(``app.modules.attendance.service.AttendanceService``): transactional
bulk-save, teacher-ownership authorization with the existing
concealment convention, atomic success-audit logging, and independently
transacted blocked-audit logging. No FastAPI routers, CSV export, or
statistics/detail/daily endpoints exist yet — see
docs/HANDOVER_PHASE_4_STAGE_2.md.
"""
