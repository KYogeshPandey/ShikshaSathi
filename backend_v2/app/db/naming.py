"""Shared SQLAlchemy naming convention.

Applying this consistently means Alembic autogenerate produces stable,
predictable constraint/index names instead of database-assigned defaults
that vary across runs and make migration diffs harder to read. This is a
widely-used, conventional naming scheme (recommended directly in the
SQLAlchemy and Alembic documentation), not a project-specific invention.
"""

from sqlalchemy import MetaData

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
