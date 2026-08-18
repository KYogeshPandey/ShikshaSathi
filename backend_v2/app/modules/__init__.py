"""Domain modules.

Each ``modules/<name>/`` package follows the shape described in
docs/ARCHITECTURE.md §2: ``models.py``, ``schemas.py``, ``repository.py``,
``service.py``, and (where the module exposes HTTP endpoints) a
``router.py``. Phase 2 adds the first two modules: ``users`` (the identity
record) and ``auth`` (authentication, tokens, sessions, RBAC).
"""
