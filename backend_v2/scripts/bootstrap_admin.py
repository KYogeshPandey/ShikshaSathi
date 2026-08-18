"""Create (or reset) the first admin user. Never hardcodes a credential.

There is no self-registration endpoint in Phase 2 (see
docs/adr/0006-identity-and-auth-foundations.md and
docs/IMPLEMENTATION_PLAN.md's Phase 2 scope), so this script is the only
way to create a user at all right now. It:

- Reads ``ADMIN_BOOTSTRAP_EMAIL`` / ``ADMIN_BOOTSTRAP_PASSWORD`` from the
  environment/``.env`` (via the normal ``Settings``) if present;
  otherwise prompts interactively — email via ``input()``, password via
  ``getpass.getpass()`` so it is never echoed to the terminal or stored
  in shell history.
- Never prints, logs, or otherwise persists the raw password anywhere.
- Is idempotent: if a user with that email already exists, it reports
  that and makes no change, unless ``--force`` is passed, in which case
  it resets that user's password, promotes them to admin, and
  reactivates the account.

Usage (run against a database that already has Phase 2's migration
applied — ``alembic upgrade head``):

    # Interactive (recommended for a real deployment):
    python -m scripts.bootstrap_admin

    # Non-interactive (e.g. scripted first-time provisioning):
    ADMIN_BOOTSTRAP_EMAIL=admin@example.com \\
    ADMIN_BOOTSTRAP_PASSWORD='a-strong-real-password-1' \\
    python -m scripts.bootstrap_admin

    # Reset an existing admin's password:
    python -m scripts.bootstrap_admin --force

Run from within the ``backend_v2`` directory (or the ``backend_v2``
container), with the same environment/``.env`` the API itself uses for
``DATABASE_URL``.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

# Allows `python scripts/bootstrap_admin.py` to work even when not
# invoked as `python -m scripts.bootstrap_admin` from backend_v2/.
sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_engine
from app.modules.auth.security import hash_password, validate_password_strength
from app.modules.users.models import UserRole
from app.modules.users.normalization import normalize_email
from app.modules.users.repository import UserRepository

_DEFAULT_ADMIN_FULL_NAME = "Administrator"


async def _run(*, force: bool) -> None:
    settings = get_settings()

    raw_email = settings.ADMIN_BOOTSTRAP_EMAIL or input("Admin email: ")
    email = normalize_email(raw_email)

    raw_password = settings.ADMIN_BOOTSTRAP_PASSWORD or getpass.getpass("Admin password: ")
    validate_password_strength(raw_password)
    password_hash = hash_password(raw_password)
    # `raw_password` is not referenced again below.

    engine = get_engine(settings)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with session_factory() as session:
        repository = UserRepository(session)
        existing = await repository.get_by_email(email)

        if existing is not None and not force:
            print(
                f"A user with email {email} already exists (id={existing.id}, "
                f"role={existing.role.value}). Pass --force to reset their "
                "password and promote/reactivate them as an admin."
            )
            return

        if existing is not None and force:
            existing.password_hash = password_hash
            existing.role = UserRole.ADMIN
            existing.is_active = True
            await session.commit()
            print(f"Updated existing user {email} (id={existing.id}) to an active admin.")
            return

        user = await repository.create(
            email=email,
            password_hash=password_hash,
            full_name=_DEFAULT_ADMIN_FULL_NAME,
            role=UserRole.ADMIN,
        )
        await session.commit()
        print(f"Created admin user {email} (id={user.id}).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the first ShikshaSathi v2 admin user. Never hardcodes a credential."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="If the user already exists, reset their password and make them an active admin.",
    )
    args = parser.parse_args()
    asyncio.run(_run(force=args.force))


if __name__ == "__main__":
    main()
