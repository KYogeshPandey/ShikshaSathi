"""The single authoritative place classroom/subject code normalization happens.

Mirrors ``app.modules.users.normalization.normalize_email``: one function,
imported everywhere a code is compared, stored, or looked up (schemas,
repositories), so ``.strip().lower()``-plus-whitespace-collapsing logic is
never re-implemented ad hoc in more than one place.
"""

from __future__ import annotations

import re

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_code(code: str) -> str:
    """Return the canonical form of a classroom/subject code.

    Stripped, lower-cased, and every run of internal whitespace collapsed
    to a single underscore (so ``"Grade 8"`` and ``"grade_8"`` normalize to
    the same stored value, matching the legacy app's own
    ``.strip().replace(" ", "_").lower()`` convention for classroom/subject
    codes — see ``backend/app/models/classroom.py`` /
    ``backend/app/models/subject.py``).

    The lower-casing half of this is also independently enforced by each
    table's own ``ck_*_code_lowercase`` CHECK constraint, the same
    belt-and-suspenders pattern as ``ck_users_email_lowercase``.
    """
    return _WHITESPACE_RUN.sub("_", code.strip()).lower()


def normalize_name(name: str) -> str:
    """Trim a display name and collapse internal whitespace runs.

    Applied to free-text display fields (classroom/subject ``name``,
    announcement ``title``) that are not identifiers and are therefore not
    lower-cased — only whitespace-normalized.
    """
    return _WHITESPACE_RUN.sub(" ", name.strip())
