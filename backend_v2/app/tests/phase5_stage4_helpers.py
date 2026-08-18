"""Direct ORM helpers for Phase 5 Stage 4 recognition tests.

These deliberately avoid the known Stage 2 ``create_sample`` MissingGreenlet
path while producing the same ACTIVE/PROCESSED state Stage 3 matching reads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.face_recognition.repository import BiometricEmbeddingRepository
from app.tests.phase5_stage3_helpers import seed_active_sample_direct


async def seed_processed_embedding_direct(
    session: AsyncSession,
    *,
    student_profile_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    embedding_values: list[float],
) -> uuid.UUID:
    sample_id = await seed_active_sample_direct(
        session,
        student_profile_id=student_profile_id,
        created_by_user_id=created_by_user_id,
    )
    samples = BiometricSampleRepository(session)
    sample = await samples.get_by_id(sample_id)
    if sample is None:  # pragma: no cover - direct-seed invariant
        raise RuntimeError("direct-seeded sample disappeared")
    await samples.mark_processed(sample, completed_at=datetime.now(UTC))
    await BiometricEmbeddingRepository(session).create_active(
        biometric_sample_id=sample.id,
        provider_name="stage4_fake",
        model_identifier="stage4_fake_model",
        model_version="test-v1",
        embedding_values=embedding_values,
        model_artifact_checksum=None,
    )
    await session.commit()
    return sample_id


__all__ = ["seed_processed_embedding_direct"]
