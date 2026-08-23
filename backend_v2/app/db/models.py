"""Import every ORM model so SQLAlchemy and Alembic share complete metadata.

Phase 3 Stage 1 added the academic domain (``app.modules.academics``),
role-linked profiles (``app.modules.profiles``), and announcements
(``app.modules.announcements``) to the Phase 2 identity/auth models
already registered here. Phase 4 Stage 1 adds attendance core and the
audit trail (``app.modules.attendance``). Phase 5 Stage 2 adds biometric
enrollment/sample models (``app.modules.biometric_enrollment``). Phase 5
Stage 3 adds the persisted embedding model; Stage 4 adds the safe recognition
attendance-attempt lifecycle model. Detection/alignment/matching remain
stateless. Every model must be
imported somewhere before ``Base.metadata``/``alembic/env.py``'s
``target_metadata`` is used, or Alembic autogenerate silently sees an
incomplete schema — this module is that one place.
"""

from app.modules.academics.models import (
    Classroom,
    DayOfWeek,
    Subject,
    TeacherAssignment,
    TimetableEntry,
)
from app.modules.announcements.models import (
    Announcement,
    AnnouncementAudience,
    AnnouncementClassroom,
)
from app.modules.attendance.models import (
    AttendanceRecord,
    AttendanceStatus,
    AuditLog,
    AuditOutcome,
)
from app.modules.auth.models import OtpChallenge, OtpPurpose, RefreshSession
from app.modules.biometric_enrollment.models import (
    BiometricEnrollment,
    BiometricSample,
    EnrollmentStatus,
    RecognitionProcessingState,
    SampleStatus,
)
from app.modules.face_recognition.models import (
    BiometricEmbedding,
    RecognitionAttendanceAttempt,
    RecognitionAttendanceReview,
)
from app.modules.profiles.models import StudentProfile, TeacherProfile
from app.modules.users.models import User

__all__ = [
    "Announcement",
    "AnnouncementAudience",
    "AnnouncementClassroom",
    "AttendanceRecord",
    "AttendanceStatus",
    "AuditLog",
    "AuditOutcome",
    "BiometricEmbedding",
    "BiometricEnrollment",
    "BiometricSample",
    "Classroom",
    "DayOfWeek",
    "EnrollmentStatus",
    "OtpChallenge",
    "OtpPurpose",
    "RecognitionAttendanceAttempt",
    "RecognitionAttendanceReview",
    "RecognitionProcessingState",
    "RefreshSession",
    "SampleStatus",
    "StudentProfile",
    "Subject",
    "TeacherAssignment",
    "TeacherProfile",
    "TimetableEntry",
    "User",
]
