# ADR 0002: Use PostgreSQL for the primary datastore

## Status
Accepted

## Context
The legacy app uses MongoDB Atlas (free tier) via `pymongo`, with no schema enforcement at the database layer — documents are built as plain dicts in `models/*.py`. This has already caused a real, observed data-integrity problem: some user documents were written with an inconsistent field name (`password` instead of `password_hash`), requiring an ad hoc, uncommitted repair script (`backend/fix_db.py`) to patch existing records after the fact (`docs/AUDIT.md` §1.4, and the Legacy Migration Map's "Authentication" row). There is no migration tooling — `backend/migrations/README.md` is an empty placeholder (`docs/AUDIT.md` §1.7). The domain itself (users, classrooms, subjects, students, attendance records, timetable entries) is fundamentally relational: attendance rows reference a student, a classroom, and a date; reports aggregate across those relations. None of that benefits from a document model.

## Decision
Move the primary datastore to PostgreSQL, accessed via SQLAlchemy 2 with Alembic-managed migrations.

## Alternatives considered
- **Keep MongoDB, add schema validation (e.g., MongoDB's JSON Schema validators) and a proper migration tool.** Rejected: this narrows but doesn't remove the mismatch between a document store and a genuinely relational domain, and the team would still be building relational integrity (foreign-key-style guarantees) on top of a database that doesn't enforce it natively.
- **MySQL/MariaDB.** Viable alternative relational option; PostgreSQL preferred for its stronger native JSON column support (useful for semi-structured fields like face-embedding vectors, if the chosen face-recognition provider stores them relationally — `docs/adr/0005-face-recognition-provider-pending.md`) and broader alignment with the rest of the target stack's tooling (Alembic, SQLAlchemy 2 async support).
- **Keep both** (Postgres for core domain data, MongoDB for biometric/face data). Deferred, not rejected outright — see `docs/LEGACY_MIGRATION_MAP.md` "Explicitly deferred decisions." Revisit once the face-recognition provider is chosen in Phase 5.

## Consequences
- Real migrations (Alembic) replace one-off scripts like `debug_db.py`/`fix_db.py` — those scripts are documented and preserved as reference (`docs/AUDIT.md` §1.4) rather than deleted, but their pattern (manual, uncommitted, run-when-someone-remembers) is not carried forward.
- A one-time data migration from the existing MongoDB Atlas cluster is required before cutover (`docs/ARCHITECTURE.md` §13); this is new work, not a "port."
- Schema is enforced at the database layer for the first time — the `password`/`password_hash` class of bug becomes structurally harder to reintroduce.
- Existing MongoDB Atlas free-tier hosting (mentioned in `README.md`'s stated tech stack) is no longer applicable; hosting choice for Postgres is a Phase 1 decision.
