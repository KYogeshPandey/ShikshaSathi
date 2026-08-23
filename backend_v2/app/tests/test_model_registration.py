"""Regression tests for ORM importability and Alembic metadata registration."""

from app.db.base import Base
from app.db.models import OtpChallenge, RefreshSession, User
from app.modules.auth.models import OtpChallenge as DirectOtpChallenge
from app.modules.auth.models import RefreshSession as DirectRefreshSession
from app.modules.users.models import User as DirectUser


def test_orm_model_modules_import_without_dataclass_mapping_errors() -> None:
    assert DirectUser is User
    assert DirectRefreshSession is RefreshSession
    assert DirectOtpChallenge is OtpChallenge


def test_phase2_tables_are_registered_in_base_metadata() -> None:
    assert {"users", "refresh_sessions", "otp_challenges"}.issubset(Base.metadata.tables)
