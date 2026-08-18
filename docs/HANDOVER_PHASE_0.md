# Handover — Rebuild Phase 0 Complete

**Phase completed:** Rebuild Phase 0 (audit/cleanup/architecture/planning) for ShikshaSathi v2. No app code was rewritten; this was documentation + safe cleanup only.
**Repo state:** legacy Flask+MongoDB+CRA app, `main` @ `c64fa9b`, still has 90 modified/5 deleted/2 untracked (`backend/debug_db.py`, `fix_db.py`) files from **before** this session — not a clean baseline. No commit was made.
**Legacy vs rebuild:** "Legacy Phase 0" (git commit "Phase 0 complete: Stable auth...") ≠ this rebuild's Phase 0. Don't confuse them.
**Read first, in order:** `docs/AUDIT.md` → `docs/LEGACY_MIGRATION_MAP.md` → `docs/ARCHITECTURE.md` → `docs/adr/*` → `docs/IMPLEMENTATION_PLAN.md` (Phase 1 section) → `docs/PROGRESS.md`.
**Created:** `docs/{AUDIT,LEGACY_MIGRATION_MAP,ARCHITECTURE,IMPLEMENTATION_PLAN,PROGRESS,HANDOVER_PHASE_0}.md`, `docs/adr/0001-0005`, `backend/.env.example`.
**Modified:** only `.gitignore` (added env/cache/debug-file patterns).
**Removed (safe, generated/unsafe only):** `__pycache__/`, `*.pyc`, and 3 debug `.txt` files that leaked a live MongoDB credential.
**Critical findings (see AUDIT.md for evidence):** C1 leaked Mongo credential (files deleted, **credential itself needs rotation — human action, not done here**); C2 JWT secret has an insecure hardcoded fallback; C3 Student portal crashes at runtime (`StudentRoutes.jsx`/`StudentLayout.jsx` empty but imported); C4 no object-level auth on attendance (any teacher can read/write any classroom).
**Architecture:** FastAPI + PostgreSQL/SQLAlchemy2/Alembic + React/TS/Vite, modular monolith, Docker Compose. Face-recognition provider is **explicitly undecided** (ADR 0005, Pending) — legacy has zero working face-recognition code despite README claiming it's the headline feature.
**Must NOT be redone:** the audit/inspection (already grounded and evidenced — re-verify specific claims if in doubt, don't re-run the whole pass blind).
**Must NOT be deleted:** `.git/` (real history), `backend/debug_db.py` / `fix_db.py` (real diagnostic/repair logic, documented not ported), anything currently tracked/uncommitted without inspecting it first.
**Recommended first Phase 1 task:** `core/config.py` (Pydantic Settings) + FastAPI skeleton + Postgres via Docker Compose, with startup failing loudly on missing config — this is the structural fix for C2's insecure fallback.
**Commands already run:** full inventory in `docs/PROGRESS.md` → "Commands run". Key result: **no network egress in this sandbox** — `pip`/`npm` real installs both failed (confirmed, not assumed), so no app boot, no `pytest`, no `npm build/test` were possible. Only `python3 -m py_compile` (syntax-only) ran clean across all backend files.
**Failed/unavailable checks:** live app run, pytest, npm build/test, API_DOCS.md verification against a running server — all blocked by no network, not by any code defect found.
