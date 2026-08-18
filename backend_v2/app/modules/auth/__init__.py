"""Authentication, token, session, and RBAC module.

- ``security.py`` — password hashing (Argon2id), JWT access tokens,
  opaque refresh-token generation/hashing.
- ``models.py`` — ``RefreshSession``, the server-side record backing
  refresh-token rotation and revocation.
- ``repository.py`` — data access for refresh sessions.
- ``service.py`` — login/refresh/logout orchestration and transaction
  ownership.
- ``dependencies.py`` — ``get_current_user`` / ``get_current_active_user``
  / ``require_roles`` FastAPI dependencies, reusable by any future
  router.
- ``router.py`` — ``POST /auth/login``, ``POST /auth/refresh``,
  ``POST /auth/logout``, ``GET /auth/me``.

See docs/adr/0006-identity-and-auth-foundations.md for the design
decisions behind all of the above.
"""
