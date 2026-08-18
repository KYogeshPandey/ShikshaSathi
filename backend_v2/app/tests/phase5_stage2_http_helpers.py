"""Shared seed/image helpers for Phase 5 Stage 2 biometric-enrollment tests.

Reuses ``app.tests.phase3_http_helpers`` (``seed_user``, ``auth_headers``,
``create_resource``) exactly as-is, matching
``app.tests.attendance_http_helpers``'s established pattern — only
enrollment-specific scaffolding (a classroom, one or two students, small
synthetic images built with Pillow) lives here.
"""

from __future__ import annotations

import io
from typing import Any

from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, UserRole
from app.tests.phase3_http_helpers import auth_headers, create_resource, seed_user


async def seed_enrollment_scope(
    client: AsyncClient, session: AsyncSession, *, suffix: str
) -> dict[str, Any]:
    """One classroom, an admin, a teacher (unauthorized for enrollment), two students."""
    admin = await seed_user(session, email=f"enr-admin-{suffix}@example.com", role=UserRole.ADMIN)
    teacher = await seed_user(
        session, email=f"enr-teacher-{suffix}@example.com", role=UserRole.TEACHER
    )
    student_1 = await seed_user(
        session, email=f"enr-student1-{suffix}@example.com", role=UserRole.STUDENT
    )
    student_2 = await seed_user(
        session, email=f"enr-student2-{suffix}@example.com", role=UserRole.STUDENT
    )

    classroom = await create_resource(
        client,
        path="/api/v1/classrooms",
        payload={"name": f"Enrollment Room {suffix}", "code": f"enr-room-{suffix}"},
        user=admin,
    )
    student_profile_1 = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_1.id),
            "classroom_id": classroom["id"],
            "roll_number": "01",
        },
        user=admin,
    )
    student_profile_2 = await create_resource(
        client,
        path="/api/v1/student-profiles",
        payload={
            "user_id": str(student_2.id),
            "classroom_id": classroom["id"],
            "roll_number": "02",
        },
        user=admin,
    )
    return {
        "admin": admin,
        "teacher": teacher,
        "classroom": classroom,
        "student_1": student_1,
        "student_2": student_2,
        "student_profile_1": student_profile_1,
        "student_profile_2": student_profile_2,
    }


def make_jpeg_bytes(
    *, size: tuple[int, int] = (200, 200), color: tuple[int, int, int] = (10, 20, 30)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def make_png_bytes(
    *, size: tuple[int, int] = (200, 200), color: tuple[int, int, int] = (40, 50, 60)
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


async def upload_sample(
    client: AsyncClient,
    *,
    student_profile_id: str,
    user: User,
    content: bytes,
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
    method: str = "post",
) -> Any:
    files = {"file": (filename, content, content_type)}
    url = f"/api/v1/biometric-enrollments/{student_profile_id}/samples"
    if method == "post":
        return await client.post(url, files=files, headers=auth_headers(user))
    return await client.put(f"{url}/active", files=files, headers=auth_headers(user))
