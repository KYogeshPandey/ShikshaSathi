"""Service-owned transaction boundary helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def service_transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Commit a complete service operation or roll it back on any failure.

    The ``finally`` form deliberately avoids a broad exception handler:
    the original exception propagates unchanged while an unfinished
    transaction is still rolled back.
    """
    committed = False
    try:
        yield
        await session.commit()
        committed = True
    finally:
        if not committed and session.in_transaction():
            await session.rollback()
