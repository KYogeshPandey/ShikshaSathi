"""Database infrastructure and ORM model registration.

The declarative base, naming convention, async sessions, and central model
import aggregator live in this package. Import ``app.db.models`` before reading
``Base.metadata`` in tooling such as Alembic so all Phase 2 tables are
registered.
"""
