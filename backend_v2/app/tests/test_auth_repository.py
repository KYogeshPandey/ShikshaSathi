"""Unit coverage for refresh-session repository query semantics."""

from collections.abc import Callable
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.repository import RefreshSessionRepository


async def test_refresh_lookup_can_request_a_database_row_lock() -> None:
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    repository = RefreshSessionRepository(cast(AsyncSession, session))
    await repository.get_by_token_hash("a" * 64, for_update=True)

    statement = session.execute.await_args.args[0]
    dialect_factory = cast(Callable[[], Dialect], postgresql.dialect)
    compiled = str(statement.compile(dialect=dialect_factory()))
    assert "FOR UPDATE" in compiled
