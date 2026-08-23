"""Explicit CLI for the deterministic Milestone 4 demo dataset.

Run from ``backend_v2`` after migrations are current:

    python -m scripts.seed_demo_data --dry-run
    python -m scripts.seed_demo_data
    python -m scripts.seed_demo_data --reset-demo

The password comes from ``DEMO_SEED_PASSWORD`` or a non-echoing prompt.
It is never printed. Production mutation is refused unless
``DEMO_SEED_ALLOW_PRODUCTION=true`` is deliberately configured.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import date
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_engine
from app.modules.auth.security import validate_password_strength
from app.modules.demo_data.service import (
    assert_demo_seeding_allowed,
    demo_manifest_counts,
    seed_demo_data,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD format.") from exc


async def _run(*, dry_run: bool, reset_demo: bool, anchor: date | None) -> None:
    settings = get_settings()
    assert_demo_seeding_allowed(settings, dry_run=dry_run)
    effective_anchor = anchor or date.today()
    if dry_run:
        print(f"Demo seed dry run (attendance anchor: {effective_anchor.isoformat()}):")
        for table_name, count in demo_manifest_counts(anchor=effective_anchor).items():
            print(f"  {table_name}: {count}")
        print("No database changes were made.")
        return

    raw_password = settings.DEMO_SEED_PASSWORD or getpass.getpass("Demo user password: ")
    validate_password_strength(raw_password)

    engine = get_engine(settings)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as session:
        result = await seed_demo_data(
            session,
            settings=settings,
            raw_password=raw_password,
            anchor=effective_anchor,
            reset_demo=reset_demo,
        )

    print(
        "Demo dataset ready: "
        f"{result.created} created, {result.updated} updated, "
        f"{result.reset_rows_removed} demo-owned rows removed during reset."
    )
    print(
        "Attendance history: "
        f"{result.attendance_start.isoformat()} through {result.attendance_end.isoformat()}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the deterministic ShikshaSathi demo data.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the manifest counts without connecting to or changing the database.",
    )
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="Restore known demo history/relationships before reseeding; never deletes other data.",
    )
    parser.add_argument(
        "--attendance-anchor",
        type=_parse_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Override today's deterministic attendance-window anchor.",
    )
    args = parser.parse_args()
    asyncio.run(
        _run(
            dry_run=args.dry_run,
            reset_demo=args.reset_demo,
            anchor=args.attendance_anchor,
        )
    )


if __name__ == "__main__":
    main()
