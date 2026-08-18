"""Unit tests for the Stage 2 service transaction boundary."""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import service_transaction


class _RecordingSession:
    def __init__(self, *, commit_fails: bool = False) -> None:
        self.commit_fails = commit_fails
        self.commits = 0
        self.rollbacks = 0
        self._in_transaction = True

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_fails:
            raise RuntimeError("simulated commit failure")
        self._in_transaction = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self._in_transaction = False

    def in_transaction(self) -> bool:
        return self._in_transaction


async def test_service_transaction_commits_after_success() -> None:
    session = _RecordingSession()
    async with service_transaction(cast(AsyncSession, session)):
        assert session.commits == 0
    assert session.commits == 1
    assert session.rollbacks == 0


async def test_service_transaction_rolls_back_and_preserves_operation_error() -> None:
    session = _RecordingSession()
    with pytest.raises(ValueError, match="operation failed"):
        async with service_transaction(cast(AsyncSession, session)):
            raise ValueError("operation failed")
    assert session.commits == 0
    assert session.rollbacks == 1


async def test_service_transaction_rolls_back_when_commit_fails() -> None:
    session = _RecordingSession(commit_fails=True)
    with pytest.raises(RuntimeError, match="commit failure"):
        async with service_transaction(cast(AsyncSession, session)):
            assert session.commits == 0
    assert session.commits == 1
    assert session.rollbacks == 1
