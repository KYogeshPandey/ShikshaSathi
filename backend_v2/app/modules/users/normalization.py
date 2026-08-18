"""The single authoritative place email normalization happens.

Every caller that will eventually compare, store, or look up an email —
``LoginRequest`` (app/modules/auth/schemas.py), ``UserRepository``
(app/modules/users/repository.py), and ``scripts/bootstrap_admin.py`` —
imports this one function rather than re-implementing ``.strip().lower()``
in three places (instruction G: "Normalize emails consistently in one
authoritative location."). Kept in its own module with zero project
imports so nothing importing it ever risks a circular import.
"""

from __future__ import annotations


def normalize_email(email: str) -> str:
    """Return the canonical form of ``email``: stripped and lower-cased.

    The lower-casing half of this is also independently enforced by the
    database's ``ck_users_email_lowercase`` CHECK constraint (see
    app/modules/users/models.py) — both exist so a bug in one layer
    doesn't silently reintroduce case-sensitive duplicate accounts.
    """
    return email.strip().lower()
