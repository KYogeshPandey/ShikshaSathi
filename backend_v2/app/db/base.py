"""Declarative base for all future ORM models.

No domain models are defined in Phase 1 (see docs/IMPLEMENTATION_PLAN.md,
Phase 1 scope: "Do not create business/domain models"). This module
exists so Phase 3+ has a single, consistent base class — with the naming
convention from app/db/naming.py already applied — for every model to
inherit from, and so Alembic's ``target_metadata`` (see alembic/env.py)
has something real to import even while it is currently empty.
"""

from sqlalchemy.orm import DeclarativeBase

from app.db.naming import metadata


class Base(DeclarativeBase):
    """Shared declarative base. All future ORM models inherit from this."""

    metadata = metadata
