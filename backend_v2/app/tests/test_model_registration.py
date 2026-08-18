"""Regression tests for ORM importability and Alembic metadata registration."""

from app.db.base import Base
from app.db.models import RefreshSession, User
from app.modules.auth.models import RefreshSession as DirectRefreshSession
from app.modules.users.models import User as DirectUser


def test_orm_model_modules_import_without_dataclass_mapping_errors() -> None:
    assert DirectUser is User
    assert DirectRefreshSession is RefreshSession


def test_phase2_tables_are_registered_in_base_metadata() -> None:
    assert {"users", "refresh_sessions"}.issubset(Base.metadata.tables)
