"""Unit tests for precise users-repository integrity-error mapping."""

from sqlalchemy.exc import IntegrityError

from app.modules.users.repository import _is_email_unique_violation


class _DriverError(Exception):
    def __init__(self, *, constraint_name: str | None = None) -> None:
        super().__init__(constraint_name or "driver integrity error")
        self.constraint_name = constraint_name


def _integrity_error(original: Exception) -> IntegrityError:
    return IntegrityError("INSERT", {}, original)


def test_email_unique_constraint_is_recognized_by_name() -> None:
    error = _integrity_error(_DriverError(constraint_name="uq_users_email"))
    assert _is_email_unique_violation(error) is True


def test_unrelated_integrity_constraint_is_not_misreported_as_email_conflict() -> None:
    error = _integrity_error(_DriverError(constraint_name="ck_users_email_lowercase"))
    assert _is_email_unique_violation(error) is False


def test_adapter_message_fallback_recognizes_email_constraint() -> None:
    error = _integrity_error(
        Exception('duplicate key value violates unique constraint "uq_users_email"')
    )
    assert _is_email_unique_violation(error) is True
