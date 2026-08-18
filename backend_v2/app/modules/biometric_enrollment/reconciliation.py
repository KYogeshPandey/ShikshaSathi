"""Database/filesystem drift detection for biometric enrollment storage.

This module only **reports** findings — it never deletes a file, never
changes a database row, and is not an always-running worker (this
application has no worker/scheduler architecture to hook into; see
docs/HANDOVER_PHASE_5_STAGE_2.md's "known risks" for how this is
expected to be invoked — an admin-only API route today, a scheduled job
in a later phase if ever needed). Any future *automatic* repair must be
conservative, explicit, and tested — deliberately out of scope for Stage
2, which only builds the detection/reporting half.

Every finding is scoped to an opaque storage ``key`` and/or a sample
``id`` — never a path, never image bytes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.biometric_enrollment.models import SampleStatus
from app.modules.biometric_enrollment.repository import BiometricSampleRepository
from app.modules.biometric_enrollment.schemas import ReconciliationFinding, ReconciliationReport
from app.modules.biometric_enrollment.storage import PrivateBiometricStorage


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ReconciliationService:
    """Compares ``BiometricSample`` rows against what actually exists on disk."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        storage: PrivateBiometricStorage | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._storage = storage or PrivateBiometricStorage(self._settings)
        self._samples = BiometricSampleRepository(session)

    async def generate_report(self) -> ReconciliationReport:
        findings: list[ReconciliationFinding] = []

        active_samples = await self._samples.list_by_status(SampleStatus.ACTIVE)
        quarantined_samples = await self._samples.list_by_status(SampleStatus.QUARANTINED)
        deletion_pending_samples = await self._samples.list_by_status(SampleStatus.DELETION_PENDING)
        replacement_pending_samples = await self._samples.list_by_status(
            SampleStatus.REPLACEMENT_PENDING
        )
        pending_samples = await self._samples.list_by_status(SampleStatus.PENDING)

        active_keys_on_disk = self._storage.list_active_keys()
        quarantine_keys_on_disk = self._storage.list_quarantined_keys()
        staged_keys_on_disk = self._storage.list_staged_keys()

        active_db_keys = {sample.storage_key for sample in active_samples}
        quarantined_db_keys = {sample.storage_key for sample in quarantined_samples}
        pending_db_keys = {sample.storage_key for sample in pending_samples}
        # Keys legitimately still present in active/ during an in-flight
        # transition (not yet quarantined) — excluded from "orphan file"
        # findings, but still separately reported below so an operator
        # can see how many are stuck.
        in_flight_active_keys = {
            sample.storage_key
            for sample in (*deletion_pending_samples, *replacement_pending_samples)
        }
        in_flight_quarantine_keys = {sample.storage_key for sample in deletion_pending_samples}

        for sample in active_samples:
            if sample.storage_key not in active_keys_on_disk:
                findings.append(
                    ReconciliationFinding(
                        finding_type="active_record_missing_file",
                        key=sample.storage_key,
                        sample_id=sample.id,
                        detail=(
                            "Sample is ACTIVE in the database but no file exists in the "
                            "active zone."
                        ),
                    )
                )

        for key in active_keys_on_disk - active_db_keys - in_flight_active_keys:
            findings.append(
                ReconciliationFinding(
                    finding_type="active_file_missing_record",
                    key=key,
                    detail="A file exists in the active zone with no matching ACTIVE database row.",
                )
            )

        for sample in quarantined_samples:
            if sample.storage_key not in quarantine_keys_on_disk:
                findings.append(
                    ReconciliationFinding(
                        finding_type="quarantined_record_missing_file",
                        key=sample.storage_key,
                        sample_id=sample.id,
                        detail=(
                            "Sample is QUARANTINED in the database but no file exists in the "
                            "quarantine zone (it may already have been purged without the "
                            "database row being finalized)."
                        ),
                    )
                )

        for key in quarantine_keys_on_disk - quarantined_db_keys - in_flight_quarantine_keys:
            findings.append(
                ReconciliationFinding(
                    finding_type="quarantined_file_missing_record",
                    key=key,
                    detail=(
                        "A file exists in the quarantine zone with no matching "
                        "QUARANTINED/DELETION_PENDING database row."
                    ),
                )
            )

        for key in staged_keys_on_disk - pending_db_keys:
            findings.append(
                ReconciliationFinding(
                    finding_type="staged_file_missing_record",
                    key=key,
                    detail=(
                        "A staged file exists with no matching PENDING database row "
                        "(likely an interrupted upload before the row was created)."
                    ),
                )
            )

        staging_cutoff = _utcnow() - timedelta(
            minutes=self._settings.ENROLLMENT_STAGING_TIMEOUT_MINUTES
        )
        for sample in pending_samples:
            if sample.created_at < staging_cutoff:
                findings.append(
                    ReconciliationFinding(
                        finding_type="pending_sample_stale",
                        key=sample.storage_key,
                        sample_id=sample.id,
                        detail=(
                            f"Sample has been PENDING (never promoted) for longer than "
                            f"{self._settings.ENROLLMENT_STAGING_TIMEOUT_MINUTES} minutes."
                        ),
                    )
                )

        for sample in deletion_pending_samples:
            if sample.updated_at < staging_cutoff:
                findings.append(
                    ReconciliationFinding(
                        finding_type="deletion_pending_stale",
                        key=sample.storage_key,
                        sample_id=sample.id,
                        detail=(
                            "Sample deletion has not completed within the staging timeout window."
                        ),
                    )
                )

        for sample in replacement_pending_samples:
            findings.append(
                ReconciliationFinding(
                    finding_type="replacement_pending_incomplete",
                    key=sample.storage_key,
                    sample_id=sample.id,
                    detail=(
                        "Sample was superseded by a replacement but its own retirement "
                        "(quarantine/purge) has not completed — see "
                        "docs/HANDOVER_PHASE_5_STAGE_2.md's known risks."
                    ),
                )
            )

        return ReconciliationReport(
            generated_at=_utcnow(),
            findings=findings,
            stale_pending_sample_count=sum(
                1 for finding in findings if finding.finding_type == "pending_sample_stale"
            ),
        )
