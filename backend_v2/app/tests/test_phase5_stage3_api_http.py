"""HTTP/API and privacy/security tests for the Stage 3 face-recognition router.

Same DB-backed conventions as the other ``test_phase5_stage3_*`` files.
Every assertion here is either an authorization boundary, a response-
shape/privacy guarantee, or a structural "this endpoint never touches
attendance" guard — the underlying pipeline math is already covered by
``test_face_recognition_matcher.py``/``test_phase5_stage3_processing_service.py``/
``test_phase5_stage3_matching_service.py``, so these tests do not
re-verify FOUND/UNKNOWN/AMBIGUOUS correctness.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attendance.models import AuditLog
from app.modules.users.models import UserRole
from app.tests.phase3_http_helpers import auth_headers, seed_user
from app.tests.phase5_stage2_http_helpers import (
    make_jpeg_bytes,
    seed_enrollment_scope,
    upload_sample,
)
from app.tests.phase5_stage3_helpers import (
    FakeFaceDetector,
    FakeFaceEmbedder,
    make_detected_face,
    patch_providers,
)

_BASE = "/api/v1/face-recognition"


async def _seed_active_sample(client_db, db_session, *, suffix):
    scope = await seed_enrollment_scope(client_db, db_session, suffix=suffix)
    upload = await upload_sample(
        client_db,
        student_profile_id=scope["student_profile_1"]["id"],
        user=scope["admin"],
        content=make_jpeg_bytes(),
    )
    sample_id = uuid.UUID(upload.json()["id"])
    return scope, sample_id


# --- authorization -----------------------------------------------------


async def test_process_sample_requires_authentication(client_db: AsyncClient, db_session) -> None:
    _scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api1")
    response = await client_db.post(f"{_BASE}/samples/{sample_id}/process")
    assert response.status_code == 401


async def test_process_sample_forbidden_for_teacher(client_db: AsyncClient, db_session) -> None:
    scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api2")
    response = await client_db.post(
        f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(scope["teacher"])
    )
    assert response.status_code == 403


async def test_process_sample_forbidden_for_student(client_db: AsyncClient, db_session) -> None:
    _scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api3")
    student = await seed_user(db_session, email="api3-student@example.com", role=UserRole.STUDENT)
    response = await client_db.post(
        f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(student)
    )
    assert response.status_code == 403


async def test_health_requires_admin(client_db: AsyncClient, db_session) -> None:
    teacher = await seed_user(db_session, email="api4-teacher@example.com", role=UserRole.TEACHER)
    response = await client_db.get(f"{_BASE}/health", headers=auth_headers(teacher))
    assert response.status_code == 403


async def test_match_probe_requires_admin(client_db: AsyncClient, db_session) -> None:
    student = await seed_user(db_session, email="api5-student@example.com", role=UserRole.STUDENT)
    files = {"file": ("probe.jpg", make_jpeg_bytes(), "image/jpeg")}
    response = await client_db.post(
        f"{_BASE}/match-probe",
        files=files,
        data={"candidate_student_profile_ids": [str(uuid.uuid4())]},
        headers=auth_headers(student),
    )
    assert response.status_code == 403


# --- response shape / privacy -------------------------------------------


async def test_admin_process_sample_response_contains_no_embedding_or_path(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api6")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()

    with patch_providers(detector, embedder):
        response = await client_db.post(
            f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(scope["admin"])
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"sample_id", "succeeded", "reason_code"}
    body_text = response.text.lower()
    assert "embedding" not in body_text
    assert "var/biometric_data" not in body_text
    assert "/home/" not in body_text
    assert "/etc/" not in body_text


async def test_processing_status_response_is_safe_metadata_only(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api7")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    with patch_providers(detector, embedder):
        await client_db.post(
            f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(scope["admin"])
        )

    response = await client_db.get(
        f"{_BASE}/samples/{sample_id}/status", headers=auth_headers(scope["admin"])
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "sample_id",
        "processing_state",
        "processing_started_at",
        "processing_completed_at",
        "failure_reason_code",
    }
    assert body["processing_state"] == "processed"
    assert "embedding" not in response.text.lower()


async def test_health_response_never_leaks_a_filesystem_path(
    client_db: AsyncClient, db_session
) -> None:
    admin = await seed_user(db_session, email="api8-admin@example.com", role=UserRole.ADMIN)
    response = await client_db.get(f"{_BASE}/health", headers=auth_headers(admin))
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"overall_status", "detector", "embedder"}
    for provider_key in ("detector", "embedder"):
        provider_body = body[provider_key]
        assert set(provider_body.keys()) == {"provider_name", "status", "detail"}
    body_text = response.text.lower()
    assert "/etc/" not in body_text
    assert "/var/" not in body_text
    assert "/home/" not in body_text
    assert "biometric_data" not in body_text
    # Default test settings never configure a real model path -> both
    # providers report NOT_CONFIGURED, never a raw exception or path.
    assert body["overall_status"] == "not_configured"


async def test_health_response_never_leaks_a_configured_missing_model_path(
    client_db: AsyncClient, db_session
) -> None:
    """Even when a (bogus, nonexistent) model path IS configured, the health
    response must still never echo that path back — only a generic reason."""
    admin = await seed_user(db_session, email="api8b-admin@example.com", role=UserRole.ADMIN)

    from app.core.config import FaceRecognitionProvider

    class _SettingsWithBogusPaths:
        FACE_RECOGNITION_PROVIDER = FaceRecognitionProvider.SERVER_SIDE_LOCAL
        FACE_DETECTOR_MODEL_PATH = "/etc/very-secret-directory/yunet.onnx"
        FACE_DETECTOR_MODEL_SHA256 = None
        FACE_EMBEDDER_MODEL_PATH = "/etc/very-secret-directory/dlib_model.dat"
        FACE_EMBEDDER_MODEL_SHA256 = None
        FACE_DETECTOR_INPUT_SIZE_PX = 320

    settings = _SettingsWithBogusPaths()

    with patch("app.modules.face_recognition.router.get_settings", return_value=settings):
        response = await client_db.get(f"{_BASE}/health", headers=auth_headers(admin))

    assert response.status_code == 200
    body_text = response.text.lower()
    assert "very-secret-directory" not in body_text
    assert "/etc/" not in body_text
    assert body_text.count("unavailable") >= 1 or "not_configured" in body_text


async def test_match_probe_rejects_empty_candidate_scope(
    client_db: AsyncClient, db_session
) -> None:
    admin = await seed_user(db_session, email="api9-admin@example.com", role=UserRole.ADMIN)
    files = {"file": ("probe.jpg", make_jpeg_bytes(), "image/jpeg")}
    response = await client_db.post(
        f"{_BASE}/match-probe",
        files=files,
        data={"candidate_student_profile_ids": []},
        headers=auth_headers(admin),
    )
    assert response.status_code in (400, 422)  # 400 from CandidateScopeRequiredError, or
    # 422 if FastAPI's own form-validation rejects a fully-empty list first.
    assert "embedding" not in response.text.lower()


# --- audit sanitization ---------------------------------------------------


async def test_processing_audit_log_metadata_contains_no_embedding_or_path(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api10")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    with patch_providers(detector, embedder):
        await client_db.post(
            f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(scope["admin"])
        )

    result = await db_session.execute(
        select(AuditLog)
        .where(AuditLog.entity_id == sample_id)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    audit_log = result.scalar_one_or_none()
    assert audit_log is not None
    metadata_text = str(audit_log.event_metadata).lower()
    assert "embedding" not in metadata_text
    assert "var/biometric_data" not in metadata_text
    assert audit_log.event_metadata.get("processing_result") == "processed"


# --- no attendance write ---------------------------------------------------


async def test_processing_and_matching_never_write_attendance_records(
    client_db: AsyncClient, db_session: AsyncSession
) -> None:
    scope, sample_id = await _seed_active_sample(client_db, db_session, suffix="api11")
    detector = FakeFaceDetector(results=[[make_detected_face()]])
    embedder = FakeFaceEmbedder()
    with patch_providers(detector, embedder):
        await client_db.post(
            f"{_BASE}/samples/{sample_id}/process", headers=auth_headers(scope["admin"])
        )

    files = {"file": ("probe.jpg", make_jpeg_bytes(), "image/jpeg")}
    with patch_providers(detector, embedder):
        await client_db.post(
            f"{_BASE}/match-probe",
            files=files,
            data={
                "candidate_student_profile_ids": [scope["student_profile_1"]["id"]],
            },
            headers=auth_headers(scope["admin"]),
        )

    result = await db_session.execute(text("SELECT COUNT(*) FROM attendance_records"))
    count = result.scalar_one()
    assert count == 0


def test_face_recognition_module_never_imports_attendance_service() -> None:
    """Static guard: no Stage 3 module *imports or calls* AttendanceService/
    AttendanceRecord — the dynamic test above proves no row gets written;
    this proves there is not even a code path that could call it.

    Deliberately AST-based (import statements + call expressions only),
    not a raw substring search of the whole source text: several of
    these modules' own docstrings *name* ``AttendanceService``/
    ``AttendanceRecord`` in prose explaining that they are NOT used
    (e.g. ``router.py``'s module docstring) — a bare
    ``"AttendanceService" not in source`` assertion would produce a
    false failure on exactly the sentence documenting their absence.
    Checking only real `import`/`from ... import`/call-expression nodes
    avoids that false positive while still catching the thing that
    actually matters: an executable reference.
    """
    import ast
    import inspect

    from app.modules.face_recognition import matching_service, processing_service, router

    forbidden_names = {"AttendanceService", "AttendanceRecord"}

    for module in (matching_service, processing_service, router):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        referenced_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                referenced_names.update(alias.name for alias in node.names)
                referenced_names.update(alias.asname for alias in node.names if alias.asname)
            elif isinstance(node, ast.Import):
                referenced_names.update(alias.name.split(".")[-1] for alias in node.names)
            elif isinstance(node, ast.Name):
                referenced_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced_names.add(node.attr)

        found = forbidden_names & referenced_names
        assert not found, (
            f"{module.__name__} references {found} as real code "
            "(import/name/attribute), not just documentation prose"
        )
