"""Aggregates all versioned (``settings.API_V1_PREFIX``) routers.

Phase 2 attached auth; Phase 3 Stage 2 attaches the academic/profile/
announcement routers; Phase 4 Stage 3 attaches the attendance and
audit-log routers; Phase 5 Stage 2 attaches the biometric enrollment
router; Phase 5 Stage 3 attaches the face-recognition router (sample
processing, provider health, and candidate-scoped match validation —
still no recognition-*attendance* route anywhere; that is Stage 4).
Liveness/readiness are deliberately mounted directly on the app in
app/main.py instead of here: health/readiness probes are
conventionally unversioned, since load balancers and orchestrators
expect a stable path that does not change across API versions.
"""

from fastapi import APIRouter

from app.modules.academics.assignments_router import router as assignments_router
from app.modules.academics.classrooms_router import router as classrooms_router
from app.modules.academics.subjects_router import router as subjects_router
from app.modules.academics.timetable_router import router as timetable_router
from app.modules.analytics.router import router as analytics_router
from app.modules.announcements.router import router as announcements_router
from app.modules.attendance.audit_router import router as audit_logs_router
from app.modules.attendance.router import router as attendance_router
from app.modules.auth.router import router as auth_router
from app.modules.biometric_enrollment.router import router as biometric_enrollment_router
from app.modules.bulk_imports.router import router as bulk_imports_router
from app.modules.face_recognition.router import router as face_recognition_router
from app.modules.profiles.student_router import router as student_profiles_router
from app.modules.profiles.teacher_router import router as teacher_profiles_router
from app.modules.reports.router import router as reports_router
from app.modules.student_onboarding.router import router as student_onboarding_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(classrooms_router)
api_router.include_router(subjects_router)
api_router.include_router(teacher_profiles_router)
api_router.include_router(student_profiles_router)
api_router.include_router(assignments_router)
api_router.include_router(timetable_router)
api_router.include_router(announcements_router)
api_router.include_router(bulk_imports_router)
api_router.include_router(attendance_router)
api_router.include_router(reports_router)
api_router.include_router(analytics_router)
api_router.include_router(audit_logs_router)
api_router.include_router(biometric_enrollment_router)
api_router.include_router(face_recognition_router)
api_router.include_router(student_onboarding_router)
