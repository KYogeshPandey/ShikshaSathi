# ShikshaSathi v2 Rebuild Progress

## Current phase
Phase 9 is COMPLETE.
Deployable MVP complete.
Phases 0-9 complete.
Milestone 2 NOT STARTED.
The Phase 0-8 sections below remain preserved as historical records.

Everything from here through the end of the "Phase 1 Verification Patch" section is the **Phase 0/1 historical record** — preserved as-is, not redone. Phase 0/1's own open human-action items (MongoDB credential rotation; the legacy `teacher_service.py` plaintext-password print) were **not** resolved by Phase 2 and remain open — see Phase 2's "Known risks" section at the end of this file.

## Legacy repository baseline
- **Branch:** `main`
- **Latest commit:** `c64fa9b` — "little bit work complete of teacher dashboard" (12 commits total on this branch; remote `github.com/KYogeshPandey/ShikshaSathi.git`)
- **Dirty working-tree summary (at session start, before any Phase 0 action):** 90 modified files, 5 deleted files (all Create React App boilerplate: `App.css`, `App.test.js`, `logo.svg`, `main.jsx`, `setupTests.js`), 5 untracked files (`backend/debug_db.py`, `backend/fix_db.py`, `debug_output.txt`, `debug_output_safe.txt`, `debug_result.txt`).
- **Legacy stack:** Flask 3.0 + MongoDB (pymongo) + JWT (flask-jwt-extended) backend; React 19 + Create React App + Tailwind CSS frontend. Full detail in `docs/AUDIT.md`.
- **Existing functional areas:** Auth (login), Admin CRUD (students/teachers/classrooms/subjects), Teacher attendance marking + stats, Timetable, Announcements, Reports, Audit log (in-app feature), CSV/Excel bulk import. **Not functional:** Student-facing frontend (routing/layout empty — Critical finding C3), face recognition (entirely unimplemented — High finding H3).

## Completed
1. Inspected the full repository (backend + frontend + git metadata) and produced a grounded, evidence-based audit — `docs/AUDIT.md`.
2. Inspected the three flagged files before any cleanup decision, per the Phase 0 brief:
   - `backend/debug_db.py` — real diagnostic logic (dumps user password-field state), kept, documented, not deleted.
   - `backend/fix_db.py` — real one-off data-repair logic (renames legacy `password` field to `password_hash`), kept, documented, not deleted.
   - `.vscode/settings.json` — benign editor config, no secrets, left in place.
3. Found and handled a live credential leak: `debug_output.txt` and `debug_output_safe.txt` contained a plaintext MongoDB Atlas connection string (username + password), traced to a `print()` statement in `backend/app/core/db.py`. `debug_result.txt` contained partial password-hash values from a live-looking user collection. All three were untracked, never committed (verified via `git log --all -p`), and have been deleted from the working tree. The source `print()` line itself was **not** modified (out of Phase 0's cleanup-of-generated-artifacts scope) — flagged as the top item in `docs/AUDIT.md` and this file's "Critical findings" below for immediate human action.
4. Removed all `__pycache__/` directories (14) and `.pyc` files (113 at time of removal — this count is inflated by a `py_compile` syntax-check sweep run during this same session, in addition to pre-existing cache files).
5. Updated `.gitignore` — added `.env.*` handling (with an explicit exception for `.env.example`), test/coverage caches, biometric/upload working-data paths, and a pattern to prevent the `debug_*.txt` credential-leak class of file from recurring.
6. Created `backend/.env.example` — grounded in an actual grep of every `os.getenv`/`process.env.REACT_APP_*` call in the codebase (only `MONGODB_URI`, `JWT_SECRET`, `REACT_APP_API_URL` are currently read; everything else in the file is explicitly marked "reserved, not yet wired to code").
7. Created `docs/LEGACY_MIGRATION_MAP.md` classifying every module listed in the Phase 0 brief.
8. Created `docs/ARCHITECTURE.md` describing the target FastAPI/PostgreSQL/React-TypeScript-Vite modular monolith, with every design choice tied back to a specific audit finding.
9. Created five ADRs under `docs/adr/`, including `0005` left explicitly `Proposed/Pending` with evaluation criteria only, no provider selected.
10. Created `docs/IMPLEMENTATION_PLAN.md` covering Phases 0–9 and both milestones.
11. Created this file and `docs/HANDOVER_PHASE_0.md`.
12. Ran the validation checks in "Commands run" below and recorded results (including failures) truthfully.

## Files created
- `docs/AUDIT.md`
- `docs/LEGACY_MIGRATION_MAP.md`
- `docs/ARCHITECTURE.md`
- `docs/adr/0001-use-fastapi.md`
- `docs/adr/0002-use-postgresql.md`
- `docs/adr/0003-use-react-typescript-vite.md`
- `docs/adr/0004-use-modular-monolith.md`
- `docs/adr/0005-face-recognition-provider-pending.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md` (this file)
- `docs/HANDOVER_PHASE_0.md`
- `backend/.env.example`

## Files modified
- `.gitignore` — see "Completed" #5 above for exactly what was added.
No other source files were modified. Note the pre-existing 90 files already shown as modified by `git status` at session start are **legacy uncommitted changes from before this session** (see "Legacy repository baseline" above) — Phase 0 did not touch application source code.

## Files removed
- `debug_output.txt` — untracked; contained a plaintext MongoDB credential (leaked via `core/db.py`'s debug print). Safe to remove: generated debug artifact, never committed, superseded by the now-documented finding in `docs/AUDIT.md` §1.4.
- `debug_output_safe.txt` — same content/reasoning as above (despite the filename, it was not actually safe).
- `debug_result.txt` — untracked; contained partial password-hash values dumped by `backend/debug_db.py`. Same reasoning: generated, never committed, unsafe to retain.
- 14 `__pycache__/` directories and 113 `.pyc` files — standard Python bytecode cache, regenerable, already covered by `.gitignore`, never committed.

## Critical findings
(Full detail and evidence in `docs/AUDIT.md`; summarized here for visibility.)
1. **Live MongoDB credential was exposed on disk** via a debug print in `backend/app/core/db.py`. The exposing files are now deleted, but **the credential itself should be rotated immediately** — this is independent of rebuild phasing and does not wait for Phase 1.
2. **JWT secret has an insecure hardcoded fallback** (`"change_this_in_env"`) in `backend/app/__init__.py`.
3. **Student portal is broken at runtime** — `frontend/src/routes/StudentRoutes.jsx` and `frontend/src/layout/StudentLayout.jsx` are empty files wired into `App.jsx`; any student login will crash on render.
4. **No object-level authorization on attendance endpoints** — any authenticated teacher can read/write attendance for any classroom, not just ones they're assigned to.

## Pending
Everything in `docs/IMPLEMENTATION_PLAN.md` Phases 1–9. Nothing in those phases has been started — no FastAPI code, no PostgreSQL, no TypeScript frontend, per Phase 0's explicit constraints. Immediately actionable items outside strict phase order:
- Rotate the MongoDB Atlas credential (human action, cannot be done from within this environment).
- Decide whether to patch the `core/db.py` debug-print line and the CORS/rate-limiting gaps in the **legacy** app as a stopgap before Phase 1/2 land, or accept the exposure window until the rebuild replaces it. Not decided here — a product/risk call for the repository owner, not an engineering-only decision.

## Known risks
- **Security:** see Critical findings above — C1–C4 in `docs/AUDIT.md`, plus High findings H1 (no rate limiting), H3 (no face recognition despite being the headline feature), H4 (zip-slip pattern in bulk photo import), H5 (open CORS).
- **Compatibility:** the legacy MongoDB documents have no enforced schema; the Phase 1 Postgres schema design will need to tolerate whatever inconsistencies exist in real data (the `password`/`password_hash` field-naming issue found via `fix_db.py` is a concrete example of this class of risk).
- **Data migration:** no migration tooling exists yet; the one-time Mongo→Postgres export/transform/load is unbuilt and unscoped beyond `docs/ARCHITECTURE.md` §13's paragraph-level plan.
- **Uncommitted legacy work:** 90 modified + 5 deleted files relative to `HEAD` predate this session and were not investigated file-by-file for intent (out of Phase 0's declared scope) — whoever resumes work should reconcile this before Phase 1 assumes a clean baseline.
- **Face recognition:** entirely unimplemented; Milestone 1 timeline depends on how quickly ADR 0005 can be resolved.
- **Deployment:** no Docker/CI exists yet (`docs/AUDIT.md` §4.4–§4.6); Phase 1/9 both have real work here, not just wiring.

## Next phase
Phase 1: Backend foundation and PostgreSQL setup (see `docs/IMPLEMENTATION_PLAN.md`).

## Commands run
Environment: sandboxed container, **no network egress** (confirmed empirically below, not assumed).
- `unzip ShikshaSathi.zip` — extracted for inspection.
- `find`, `git log --oneline -10`, `git rev-list --count HEAD`, `git branch --show-current`, `git remote -v`, `git status --short` — repository baseline (see "Legacy repository baseline").
- `cat backend/requirements.txt`, `cat frontend/package.json` — dependency inventory.
- `pip3 install --dry-run flask --break-system-packages` → reported "already satisfied" (Flask pre-installed in this sandbox image, not fetched live).
- `pip3 install pymongo flask-cors flask-jwt-extended pydantic opencv-python mtcnn bcrypt python-dotenv flask-limiter pandas pytest gunicorn --break-system-packages` → **failed**: `ERROR: Could not find a version that satisfies the requirement pymongo (from versions: none)`. Confirms no real package index reachable.
- `npm install --dry-run` (frontend) → resolved 1410 packages from the lockfile without a real fetch (dry-run only).
- `npm install` (real, frontend, timeout 20s) → **failed**: `npm error code E403 ... 403 Forbidden - GET https://registry.npmjs.org/...`. Confirms egress is genuinely blocked, not just slow. Any partial `node_modules` from this attempt was removed immediately after.
- `which pytest` / `python3 -m pytest --version` → **not installed**, could not attempt to collect/run the (empty) backend test suite.
- `find . -name "*.py" -not -path "*/__pycache__/*" | xargs python3 -m py_compile` → **all files compiled with no syntax errors** (this does not require pymongo/Flask/etc. to be installed, since compilation doesn't resolve imports — it's a genuine, if partial, verification, not a full app-boot test).
- `grep -rn "Limiter"`, `grep -rn "cv2\|mtcnn\|MTCNN\|face_recognition"`, `grep -rn "hooks/useAuth"` etc. across the backend/frontend — used to verify dead-code and unimplemented-feature findings before writing them into `docs/AUDIT.md`, rather than assuming from file names alone.
- Pattern-based secrets scan (AWS-key/Google-API-key/OpenAI-key/Mongo-URI-with-credentials/PEM-private-key patterns) across all tracked `.py`/`.js`/`.jsx`/`.json`/`.env*`/`.md` files, excluding `.git` and `node_modules` → **no matches** in tracked files (the only real secret found was in the three now-deleted untracked debug files, handled separately and never printed in full in any document produced by this session).
- `iconv -f UTF-16LE -t UTF-8` on the two UTF-16-encoded debug files, specifically to inspect them safely before deciding whether they were safe to delete.
- Cleanup commands: `find . -iname "__pycache__" -type d -exec rm -rf {} +`, `find . -iname "*.pyc" -delete`, `rm debug_output.txt debug_output_safe.txt debug_result.txt`.

### Failed or unavailable checks (recorded truthfully, not glossed over)
- Could not run the actual Flask app (pymongo and other dependencies not installable — no network).
- Could not run `pytest` (not installed, and test files are empty regardless).
- Could not run `npm run build` or `npm test` for the frontend (`node_modules` not installable — no network; confirmed with a real, non-dry-run attempt, not assumed from the sandbox's stated network policy alone).
- Could not verify `API_DOCS.md`'s claims against a live server.
- Frontend was **not** exhaustively reviewed component-by-component (17 page components, dozens of smaller components) — `docs/AUDIT.md` §3.6–§3.7 explicitly flags hardcoded-data checks, accessibility, and responsiveness as not assessed in this pass, rather than silently claiming coverage that wasn't done.

---

# Phase 1: FastAPI Backend Foundation and PostgreSQL Infrastructure

**Status: completed this session.** Implemented under `backend_v2/`, coexisting with the untouched legacy `backend/` — see `docs/ARCHITECTURE.md` §14 and `docs/HANDOVER_PHASE_1.md`.

## Completed
1. Read `docs/HANDOVER_PHASE_0.md`, `docs/PROGRESS.md` (this file), `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/AUDIT.md`, `docs/LEGACY_MIGRATION_MAP.md`, and all five ADRs under `docs/adr/` before implementing anything, per the Phase 1 brief. Did not repeat the Phase 0 audit itself.
2. Verified the Phase 1 input ZIP's `docs/` are byte-identical to the documents already on record — no drift to reconcile.
3. Inspected `backend/app/core/db.py`: the previously-flagged `print("DEBUG MONGODB_URI:", uri)` line is **already absent** in this snapshot. No source edit was needed or made; recorded here as a verification, per the Phase 1 brief's explicit instruction to check.
4. Searched the legacy backend snapshot for other direct secret-printing statements, per the brief's "also search... for other obvious direct secret-printing statements." Found one, **not** present in the original `docs/AUDIT.md`: `backend/app/services/teacher_service.py` prints a newly-created teacher's **raw plaintext password** to stdout (`print(f"✅ User created for Teacher: {email} (Pass: {raw_password})")`). **This was deliberately not patched.** The Phase 1 brief authorizes exactly one legacy modification (the `core/db.py` line above, which turned out to already be absent) and explicitly prohibits "a broad legacy-security refactor in this phase" — a second file is outside that one authorized patch. Documented here and in `docs/HANDOVER_PHASE_1.md` as an unresolved, real finding, the same way `docs/AUDIT.md` documented H4 (zip-slip) without fixing it immediately.
5. Re-confirmed `backend/.env.example` contains only placeholders, no real secret — unchanged from Phase 0.
6. Built the complete `backend_v2/` FastAPI + PostgreSQL foundation: centralized Pydantic Settings with fail-fast validation, structlog-based structured logging, request-ID correlation middleware, a standard sanitized error envelope with centralized exception handlers, async SQLAlchemy 2 engine/session plumbing, Alembic configured for async migrations with one intentionally empty baseline migration, and `GET /health/live` / `GET /health/ready` — matching `docs/IMPLEMENTATION_PLAN.md`'s Phase 1 scope exactly. No authentication, RBAC, or domain models were implemented (out of scope per the brief).
7. Wrote a real, substantive test suite (7 files, no fake assertions, no empty tests) covering settings validation, both health endpoints, the centralized exception handlers, and the request-ID middleware.
8. Created the root `docker-compose.yml` (`postgres` + `backend_v2` services only, each with a health check) and a root `.env.example`, in addition to `backend_v2/.env.example`. The split between the two `.env.example` files is deliberate (Compose-internal hostname `postgres` vs. standalone-dev hostname `localhost`) and is documented in both files and in `backend_v2/README.md`.
9. Ran every static check actually possible in this sandbox and, during a full manual correctness review of every core module (since no dependency could be installed to execute anything), found and fixed one concrete bug — see "Architecture decisions."
10. Updated `docs/ARCHITECTURE.md` (new §14) and `docs/IMPLEMENTATION_PLAN.md` (one status line on the Phase 1 header) minimally, and this file. Created `docs/HANDOVER_PHASE_1.md`.
11. Re-verified immediately before packaging: no `.env` file exists anywhere in the repository; no hardcoded secret anywhere in `backend_v2/`; no `__pycache__`/`.pyc`/lint-tool caches included in the final archive.

## Files created
`backend_v2/` (34 files):
- `pyproject.toml`
- `app/__init__.py`, `app/main.py`
- `app/api/__init__.py`, `app/api/router.py`, `app/api/routes/__init__.py`, `app/api/routes/health.py`
- `app/core/__init__.py`, `app/core/config.py`, `app/core/exceptions.py`, `app/core/logging.py`, `app/core/middleware.py`
- `app/db/__init__.py`, `app/db/base.py`, `app/db/naming.py`, `app/db/session.py`
- `app/schemas/__init__.py`, `app/schemas/error.py`, `app/schemas/health.py`
- `app/tests/__init__.py`, `app/tests/conftest.py`, `app/tests/test_config.py`, `app/tests/test_error_handling.py`, `app/tests/test_health_live.py`, `app/tests/test_health_ready.py`, `app/tests/test_middleware.py`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/20260726_1200_98161483914f_create_initial_schema_baseline.py`
- `Dockerfile`, `.dockerignore`, `.env.example`, `README.md`

Repository root (2 files):
- `docker-compose.yml`
- `.env.example` (root-level; distinct from `backend_v2/.env.example` — see both files' comments and `backend_v2/README.md`)

`docs/` (1 file):
- `docs/HANDOVER_PHASE_1.md`

Note on `app/tests/test_middleware.py`: one file beyond the brief's literal structure listing. The brief's own acceptance criteria calls out three distinct, explicit middleware behaviors to test (valid ID propagated, missing ID generated, unsafe/oversized ID replaced) — this got its own file rather than being folded into `test_error_handling.py`, which is already about a different concern (exception handlers). A minor, justified structural addition, not a deviation from anything required.

## Files modified
- `docs/ARCHITECTURE.md` — added §14 ("Phase 1 note: `backend_v2/` transitional coexistence"). No existing section text changed.
- `docs/IMPLEMENTATION_PLAN.md` — added one status line to the "Phase 1" section header. No scope, deliverable, dependency, or acceptance-criteria text changed.
- `docs/PROGRESS.md` — this file: "Current phase" updated at the top; this entire "Phase 1" section appended at the end.

No legacy `backend/` or `frontend/` source file was modified. The one legacy edit the Phase 1 brief pre-authorized (removing `core/db.py`'s debug print) was not needed, because that line was already absent — see "Completed" #3.

## Files removed
None. Nothing was deleted this phase.

## Architecture decisions
- **Health checks are unversioned.** `GET /health/live` and `GET /health/ready` mount directly on the app, not under `API_V1_PREFIX` — matching the brief's own literal `curl http://localhost:8000/health/live` examples and the convention that health probes should have a version-independent path. `app/api/router.py`'s `api_router` exists (per the required structure) and is wired to `API_V1_PREFIX` in `app/main.py`, but is intentionally empty until Phase 2's first real router lands.
- **Request-ID propagation and request logging are one middleware, not two** — they share the same timing/context. The ID-selection logic is still an independently unit-tested pure function (`_extract_safe_request_id`).
- **`require_database_ready` is its own FastAPI dependency**, separate from the plain `ping_database` infrastructure check, specifically so `GET /health/ready` is testable via `app.dependency_overrides` without a real PostgreSQL instance. `ping_database` stays untranslated (raises whatever the driver raises) so it also stays mockable at the function level for the two `pytest-asyncio` coroutine tests in `test_health_ready.py`.
- **Engines/sessionmakers are cached per `(url, echo)` pair**, not as one process-wide singleton — so overriding `get_settings` per-app in tests can't silently reuse an engine built from different settings.
- **Two separate `.env.example` files** (root and `backend_v2/`): inside the Compose network, Postgres is reachable at hostname `postgres`; standalone local development reaches it at `localhost`. One shared file can't correctly hold both values, so `docker-compose.yml` constructs `backend_v2`'s `DATABASE_URL` itself from the root `.env`'s `POSTGRES_*` values instead.
- **`hatchling` as the build backend**, with `backend_v2` itself pip-installable (`pip install -e ".[dev]"` locally; `pip install .` in the Dockerfile's builder stage) rather than a separate `requirements.txt` — keeps `pyproject.toml` the single dependency manifest.
- **`logging.basicConfig(..., force=True)`** (`app/core/logging.py`) — found during the manual review required because no dependency could be installed to actually execute anything: without `force=True`, `basicConfig` silently no-ops if the root logger already has a handler by the time `configure_logging` runs (possible depending on import order relative to uvicorn's own logging setup), which would silently defeat the structured-logging setup with no error at all. Fixed before packaging.
- **`SECRET_KEY`/`DATABASE_URL`/`POSTGRES_PASSWORD` have no defaults and are marked `Field(repr=False)`**; `SECRET_KEY` is checked against both a minimum length (32 chars) and a known-placeholder set including the legacy app's own `"change_this_in_env"` fallback and its `.env.example`'s `"replace_with_a_long_random_value"` — the direct structural closure of Critical finding C2.

## Commands run
From `backend_v2/`, actually executed in this sandbox:
- `python3 --version` → `Python 3.12.3`.
- `python3 -m compileall -q app alembic` → completed with no output (no syntax errors) across every `.py` file.
- A small Python script using stdlib `tomllib` to parse `pyproject.toml` → parsed successfully; spot-checked `project.name`, dependency counts, Ruff/mypy/pytest config keys.
- A small Python script using `yaml.safe_load` to parse `docker-compose.yml` → parsed successfully; verified only `postgres`/`backend_v2` services exist, confirmed no frontend/redis/celery/mongo/nginx service was added.
- A small Python script using `configparser` (interpolation disabled, to tolerate Alembic's `%()s` template syntax) to parse `alembic.ini` → parsed successfully; verified `sqlalchemy.url` is **not** present.
- A custom AST-based script, written for this review, that parses every `.py` file under `app/` and `alembic/`, extracts every `from app.* import ...` statement, and confirms the imported name is genuinely defined (or is a real submodule) in its target file → **27/27 internal imports verified to resolve correctly** (one false positive in the checker's own submodule handling was found and fixed first).
- `grep -rniE "(password|secret)\s*=\s*['\"a-z0-9]{6,}"` across `backend_v2/`, filtered against known-safe placeholder patterns → no unexplained hardcoded secret-looking value found.
- `find . -name ".env" -not -name ".env.example"` (repository-wide) → no output; no real `.env` exists anywhere.
- `find . -iname "__pycache__" -type d -exec rm -rf {} +` / `find . -iname "*.pyc" -delete` → cleanup after `compileall`, confirmed empty before packaging.
- Manual, line-by-line review of `app/core/config.py`, `app/core/exceptions.py`, `app/db/session.py`, `app/api/routes/health.py`, `app/core/logging.py`, `app/main.py`, `app/tests/conftest.py`, every test file, `alembic/env.py`, `Dockerfile`, and `.dockerignore` — reasoning by hand through FastAPI/Starlette middleware-and-exception-handler ordering, pydantic-settings source precedence, and Alembic's async engine recipe, since none of it could be executed. One concrete bug found and fixed (see "Architecture decisions").

## Passed checks
- `python3 --version` → 3.12.3 (satisfies the `>=3.12` requirement).
- `python3 -m compileall` on every file in `backend_v2/app/` and `backend_v2/alembic/` — zero syntax errors.
- `pyproject.toml` — valid TOML; dependency/tool-config structure confirmed programmatically.
- `docker-compose.yml` — valid YAML; service/volume/network structure confirmed programmatically; confirmed no out-of-scope services.
- `alembic.ini` — valid structure; confirmed no hardcoded `sqlalchemy.url`.
- Custom AST cross-import checker — 27/27 internal imports resolve.
- Hardcoded-secret grep sweep across `backend_v2/` — nothing found.
- Repository-wide search for a real `.env` file — none exists.
- Manual correctness review of every core module — passed, other than the one issue found and fixed.

## Failed or unavailable checks
All of the following are **environment limitations of this sandbox** (no code was written assuming they'd fail — the reasons were confirmed empirically, matching the same class of limitation Phase 0 hit and documented above):
- `pip install fastapi` (or any real package) → **failed**: `ERROR: Could not find a version that satisfies the requirement fastapi (from versions: none)`. Confirmed via `curl -D -` that the sandbox's egress proxy returns `x-deny-reason: host_not_allowed` for `pypi.org` — genuinely no network egress, not a slow/flaky network.
- `ruff format --check .` / `ruff check .` → **unavailable**: `ruff` is not installed (`No module named ruff`) and cannot be installed (no network).
- `mypy app` → **unavailable**: `mypy` is not installed and cannot be installed. The codebase was written to satisfy `[tool.mypy]`'s strict configuration, including the one narrow, named `asyncpg.*` override — but that is a design intention checked by hand, not an executed, passing type-check.
- `pytest` → **unavailable**: `pytest`/`pytest-asyncio`/`httpx`/`fastapi`/`sqlalchemy`/etc. are not installed and cannot be installed. The 7 test files are real, substantive tests (no `assert True`, nothing empty) written to exercise dependency overrides, monkeypatching, and the HTTP layer correctly by design — but they have **not been executed** in this environment.
- `alembic current` / `history` / `upgrade head` / `downgrade base` → **unavailable**: `alembic` is not installed, and no PostgreSQL instance is reachable in this sandbox regardless.
- `docker compose config` / `build` / `up -d` / `ps` / `exec ... alembic ...` / `down` → **unavailable**: Docker is not installed in this sandbox (`docker: not found`). `docker-compose.yml` was instead validated as structurally-correct YAML by hand (see "Passed checks") — a real but partial substitute.
- `curl http://localhost:8000/health/live` / `/health/ready` → **unavailable**: no running server, blocked by the same missing-dependency/no-Docker limitations above.

**No check above is claimed to have passed.** Where full execution wasn't possible, the closest available static/structural verification was performed instead and is reported separately under "Passed checks" — never conflated with the runtime check it stands in for.

## Known risks
- **Everything in this phase is statically verified, not runtime-verified.** Nobody has actually booted `backend_v2`, hit its endpoints, or run its test suite against a real interpreter with real dependencies installed. The next environment with network access and/or Docker should run the full validation command list in `backend_v2/README.md` before this code is trusted in any deployment sense.
- **`teacher_service.py`'s plaintext-password print is a real, unresolved legacy issue** (see "Completed" #4) — not fixed this phase, per the brief's tight scope. It logs a real user-chosen password to stdout every time a teacher account is created, in what is still the deployed, traffic-serving backend. This is at least as serious in kind as the original C1 finding and should get an explicit human decision — fix now as a legacy hotfix, or accept the exposure window — the same way C1's credential rotation was flagged for immediate human action rather than resolved automatically.
- **Phase 0's own flagged human actions remain open**: the MongoDB Atlas credential still needs rotation; the repository owner still hasn't decided whether to hotfix the legacy app's CORS/rate-limiting gaps. Phase 1 did not change this.
- **The 90 modified / 5 deleted legacy files relative to `HEAD`** (Phase 0 baseline, above) were not reconciled — this phase did not touch legacy source, so the baseline is exactly as uncertain as Phase 0 left it.
- **No authentication, RBAC, or domain models exist yet** — `backend_v2` cannot serve real traffic. Intentional Phase 1 scope, not a gap.
- **No MongoDB→PostgreSQL data migration exists yet** — unbuilt, unscoped beyond `docs/ARCHITECTURE.md` §13's paragraph-level plan, same as Phase 0 left it.
- **Dependency version floors in `pyproject.toml`** were chosen as reasonable, non-obsolete lower bounds; they have not been checked against whatever the actual latest compatible releases are as of this session's real date, because no package index was reachable to check against.

## Pending
Everything in `docs/IMPLEMENTATION_PLAN.md` Phases 2–9 and both Milestones. Nothing in those phases has been started. Immediately actionable items outside strict phase order (carried forward from Phase 0, still unresolved, plus one new item):
- Rotate the MongoDB Atlas credential (human action).
- Decide on a legacy hotfix vs. accept-the-window for the legacy app's CORS/rate-limiting gaps.
- **New this phase:** decide whether to patch `backend/app/services/teacher_service.py`'s plaintext-password print as a legacy hotfix, or explicitly accept that exposure window too (see "Known risks").
- Run the full validation command list in `backend_v2/README.md` in an environment with network access and/or Docker, and record real (not static-only) results.

## Next phase
Phase 2: Authentication, refresh-token security, RBAC, and object-level authorization (see `docs/IMPLEMENTATION_PLAN.md`). Recommended first task: the login endpoint + password hashing + access/refresh tokens, building directly on `backend_v2`'s Settings/session/error/logging foundation — see `docs/HANDOVER_PHASE_1.md`.


# Phase 1 Verification Patch — Local Runtime and Quality-Gate Follow-up

## Status
Phase 1 foundation remains complete. This focused follow-up records real local Docker
verification, fixes the two failures found by the first test run, and adds a reproducible
Docker-only quality-gate workflow. No Phase 2 feature was started.

## Local runtime verification completed by repository owner
- Windows 11 + WSL 2 + Docker Desktop were installed and verified with `hello-world`.
- `docker compose config` passed after correcting `CORS_ALLOWED_ORIGINS` to a JSON-array
  value in the root `.env`.
- `docker compose build` completed successfully.
- PostgreSQL 16 and `backend_v2` both reached healthy status.
- `GET /health/live` returned `{"status": "alive"}`.
- `GET /health/ready` returned `{"status": "ready", "checks": {"database": "ready"}}`.
- `alembic upgrade head` applied revision `98161483914f`.
- `alembic downgrade base`, re-upgrade to head, and `alembic current` all passed.
- The legacy plaintext-password `print()` in
  `backend/app/services/teacher_service.py` was removed before this patch snapshot.
- The repository owner reported rotating the previously exposed MongoDB database-user
  password; this cannot be independently verified from source code and no secret is stored here.

## Failures found by the first real test run
The first source-mounted Docker test run collected 45 tests: 43 passed and 2 failed.

1. `test_missing_secret_key_raises` was not isolated from the Compose-provided
   `SECRET_KEY`; removing the constructor kwarg alone allowed Pydantic Settings to read
   the process environment.
2. Unexpected exceptions were converted by the outer exception handler after
   `RequestIDMiddleware` re-raised them, so the generated error body had a request ID but
   the response lacked the configured request-ID header.

## Fixes completed
- The missing-secret test now removes `SECRET_KEY` with pytest `monkeypatch` and keeps
  dotenv disabled through the existing `_env_file=None` constructor data.
- All centralized error handlers now use one `_error_response()` helper that includes the
  request ID in both the body and configured response header while preserving HTTPException
  headers.
- `RequestIDMiddleware` stores the configured request-ID header name on `request.state` for
  centralized handlers.
- Error-handler coverage now checks unexpected, validation, application-defined, and HTTP
  errors; the suite contains 50 tests after the patch.
- CORS settings use Pydantic Settings `NoDecode`, then safely parse either a JSON array or a
  comma-separated environment value. This fixes the startup failure while keeping both
  documented forms supported.
- Root and standalone `.env.example` files now show the preferred JSON-array CORS format.
- A dedicated Docker `test` target and Compose `backend_v2_test` profile install dev-only
  dependencies and run pytest, Ruff formatting, Ruff lint, and mypy without adding those
  tools or tests to the production runtime image.
- Hatch wheel configuration excludes `app/tests` from the production wheel.

## Verification performed in the patch environment
- `python -m pytest app/tests`: **50 passed**. The artifact environment lacked the real
  `structlog` package, so this focused test run used a temporary external compatibility
  shim only for log calls; no shim is included in the repository.
- Python syntax compilation and AST parsing passed for all `backend_v2` Python files.
- TOML and YAML structural parsing passed.
- Secret/cached-artifact scan found no real `.env`, `.git`, credentials, bytecode, or test
  caches in the deliverable.
- Ruff and mypy binaries were unavailable in the artifact environment. The authoritative
  reproducible command is now:
  `docker compose --profile test run --rm backend_v2_test`.

## Files modified by this verification patch
- `backend_v2/app/core/config.py`
- `backend_v2/app/core/exceptions.py`
- `backend_v2/app/core/middleware.py`
- `backend_v2/app/schemas/error.py` (format-only line wrapping)
- `backend_v2/app/tests/test_config.py`
- `backend_v2/app/tests/test_error_handling.py`
- `backend_v2/pyproject.toml`
- `backend_v2/Dockerfile`
- `backend_v2/.dockerignore`
- `backend_v2/alembic/versions/20260726_1200_98161483914f_create_initial_schema_baseline.py`
- `backend_v2/alembic/script.py.mako`
- `backend_v2/.env.example`
- `backend_v2/README.md`
- `.env.example`
- `docker-compose.yml`
- `docs/PROGRESS.md`
- `docs/HANDOVER_PHASE_1.md`

## Remaining gate before Phase 2
On the repository owner's Docker-enabled machine, run:

```bash
docker compose --profile test build backend_v2_test
docker compose --profile test run --rm backend_v2_test
```

Expected: 50 tests pass, Ruff format passes, Ruff lint passes, and mypy passes. Any reported
Ruff or mypy issue must be fixed before beginning Phase 2.

Local Docker verification completed:
- 50 tests passed
- Ruff format check passed
- Ruff lint passed
- mypy passed for 25 source files
- 1 non-blocking StarletteDeprecationWarning remains

## Next phase
Phase 2: authentication, access/refresh-token security, RBAC, and object-level authorization.



# Phase 2: Identity, Authentication, Refresh-Token Sessions, and RBAC

**Status: completed and locally verified with Docker and PostgreSQL.** Docker and network
access were unavailable in this implementation environment — identical to Phase 0
and Phase 1's starting point — so pytest/Ruff/mypy/Alembic/Docker could not be
executed here. See "Failed or unavailable checks" below for exactly what that
means and does not mean.

## Completed
1. Read `docs/HANDOVER_PHASE_1.md`, this file, `docs/ARCHITECTURE.md`,
   `docs/IMPLEMENTATION_PLAN.md`, `docs/adr/0001-0005`, and `docs/AUDIT.md` /
   `docs/LEGACY_MIGRATION_MAP.md` before implementing anything. Did not repeat
   Phase 0's audit or Phase 1's scaffold.
2. Implemented the `users` domain: `User` ORM model (UUID PK, native
   `user_role` Postgres enum, case-insensitive email with both an
   application-layer normalizer and a DB-level `CHECK` constraint,
   `is_active`, timestamps), `UserRepository`, `UserRead` response schema
   (no `password_hash` field), and `EmailAlreadyExistsError`.
3. Implemented the `auth` domain: `RefreshSession` ORM model; Argon2id
   password hashing plus a timing-safety dummy-hash path for unknown-email
   login attempts; JWT access-token creation/validation (no role claim);
   opaque, SHA-256-hashed refresh-token generation; `RefreshSessionRepository`;
   `AuthService` (login/refresh/logout, owning the transaction boundary);
   `get_current_user` / `get_current_active_user` / `require_roles` /
   `verify_same_origin` dependencies; the `/auth` router
   (login/refresh/logout/me).
4. Wired the new router into `app/api/router.py`; updated `app/main.py`'s
   description text for Phase 2 (no behavioral change).
5. Extended `app/core/config.py`: JWT algorithm/issuer/audience/lifetimes,
   refresh-cookie name/secure/samesite/domain, admin-bootstrap email/password
   (script-only), and validators enforcing sane token lifetimes and a
   production-only `Secure`-cookie requirement.
6. Added `scripts/bootstrap_admin.py` — the one documented way to create a
   user in Phase 2 (no self-registration endpoint exists yet, per the Phase 2
   brief); reads `ADMIN_BOOTSTRAP_EMAIL`/`ADMIN_BOOTSTRAP_PASSWORD` or prompts
   interactively (`getpass`, never echoed/logged); idempotent; `--force` to
   reset/promote an existing account.
7. Wrote `alembic/versions/20260728_0900_6eeb9420bf8b_create_users_and_refresh_sessions.py`
   (down-revision `98161483914f`, the Phase 1 baseline) creating the
   `user_role` enum, `users`, and `refresh_sessions`, with explicit
   constraint/index names matching `app/db/naming.py`'s convention and both
   models' `__table_args__` exactly.
8. Extended the Docker test workflow: `docker-compose.yml` gained an isolated,
   ephemeral (`tmpfs`, no volume) `postgres_test` service and wired
   `backend_v2_test` to it (profile `test` only, never started by a plain
   `docker compose up`); the Dockerfile's `test` stage now runs
   `alembic upgrade head` before `pytest`.
9. Extended `app/tests/conftest.py` with `db_session` (a real, isolated
   Postgres session per test, built on its own `NullPool` engine to avoid
   asyncpg-connection/event-loop scoping issues, with its own connectivity
   check that skips gracefully — with a clear message — if no test database
   is reachable) and `client_db` (an HTTP client wired to that same session
   via `get_db_session` override).
10. Wrote 12 dedicated Phase 2 test files, 80 test functions total: `test_auth_security.py`
    (pure unit — password hashing/policy, email normalization, JWT
    valid/expired/malformed/wrong-signature/wrong-audience/wrong-issuer/
    wrong-type, refresh-token generation/hashing — no DB needed, always
    runs), `test_rbac_dependencies.py` (pure dependency-composition unit
    tests via a throwaway probe app — no DB or real JWT needed, always
    runs), `test_users_repository.py`, `test_auth_login.py`,
    `test_auth_access_token_http.py`, `test_auth_refresh.py`,
    `test_auth_logout.py`, `test_auth_me_and_rbac_integration.py` (all
    database-backed, skip gracefully without a reachable test Postgres),
    and `test_migrations_phase2.py` (the upgrade/downgrade/re-upgrade
    round-trip, run as a plain sync test to avoid nesting Alembic's own
    internal `asyncio.run()` inside an already-running event loop).
11. Wrote `docs/adr/0006-identity-and-auth-foundations.md` recording the
    identifier strategy, password-hashing algorithm, access-vs-refresh-token
    shape, cookie transport, and CSRF-mitigation decisions.
12. Updated both `.env.example` files (root and `backend_v2/`) with every new
    setting, and the root file with the optional `postgres_test`-only
    override variables; updated `backend_v2/README.md` and this file.
13. Ran every static check actually possible in this sandbox (see "Commands
    run" below) and fixed the one real issue they found (see "Architecture
    decisions").

## Files created
`backend_v2/app/modules/` (11 files):
`__init__.py`, `users/__init__.py`, `users/models.py`, `users/normalization.py`,
`users/schemas.py`, `users/errors.py`, `users/repository.py`,
`auth/__init__.py`, `auth/models.py`, `auth/security.py`, `auth/repository.py`,
`auth/schemas.py`, `auth/errors.py`, `auth/service.py`, `auth/dependencies.py`,
`auth/router.py` (16 files total under `modules/`).

`backend_v2/scripts/` (2 files): `__init__.py`, `bootstrap_admin.py`.

`backend_v2/alembic/versions/` (1 file):
`20260728_0900_6eeb9420bf8b_create_users_and_refresh_sessions.py`.

`backend_v2/app/tests/` (7 files): `test_auth_security.py`,
`test_rbac_dependencies.py`, `test_migrations_phase2.py`,
`test_users_repository.py`, `test_auth_login.py`,
`test_auth_access_token_http.py`, `test_auth_refresh.py`,
`test_auth_logout.py`, `test_auth_me_and_rbac_integration.py`
(12 dedicated files, 80 test functions total).

`docs/` (1 file): `docs/adr/0006-identity-and-auth-foundations.md`,
`docs/HANDOVER_PHASE_2.md`.

## Files modified
- `backend_v2/pyproject.toml` — added `pyjwt`, `argon2-cffi`,
  `email-validator`; tightened the SQLAlchemy floor to `>=2.0.30` (needed by
  the test suite's `async_sessionmaker` usage, not by application code).
- `backend_v2/app/core/config.py` — added the Phase 2 settings block and
  validators described in "Completed" #5.
- `backend_v2/app/main.py` — description text only (Phase 2 scope, not a
  behavioral change).
- `backend_v2/app/api/router.py` — mounts the new auth router.
- `backend_v2/Dockerfile` — `scripts/` copied into the builder/test/runtime
  stages; the test stage's `CMD` now runs `alembic upgrade head` first.
- `docker-compose.yml` — added `postgres_test` and `backend_v2_test`'s new
  environment/`depends_on`/`command`.
- `backend_v2/.env.example`, `.env.example` (root) — every new setting
  documented; root file also documents the optional test-database overrides.
- `backend_v2/README.md` — Phase 2 endpoints, settings, and the
  database-backed test workflow.
- `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/PROGRESS.md`
  (this file) — status lines / this section only, per the same
  minimal-edit convention Phase 1 used for its own additions.

## Files removed
None.

## Architecture decisions
- **UUID primary keys** for `users`/`refresh_sessions` — no earlier document
  mandated an identifier strategy; sequential integers would make user
  enumeration trivial once Phase 3's admin APIs exist. See ADR 0006.
- **Refresh tokens are opaque, not JWT** — only a SHA-256 digest is ever
  persisted; session metadata (owner, expiry, revocation, rotation lineage)
  lives in `refresh_sessions`, which is what makes real revocation and reuse
  detection possible without a second server-side blacklist. See ADR 0006.
- **No `role` claim in access tokens** — deliberately, so no future code path
  is ever tempted to trust a token-carried role instead of the database;
  `get_current_user` always re-loads the user row.
- **`db_session`'s test fixture uses its own `NullPool`-backed engine, created
  and disposed within a single test function** — rather than reusing the
  application's module-level cached engine (`app/db/session.py`) — to avoid a
  well-known class of bug where an asyncpg connection pool created under one
  asyncio event loop is reused from a different loop; pytest-asyncio's
  default loop scope is per-test-function, and this sidesteps that entirely
  regardless of which loop-scope configuration is in effect.
- **`test_migrations_phase2.py` is a plain `def`, not `async def`** —
  `alembic/env.py`'s online-migration path calls `asyncio.run(...)`
  internally, which raises if called from inside an already-running event
  loop; a synchronous test has no event loop of its own when it starts, so
  Alembic's internal call (and the test's own lightweight `asyncio.run()`
  calls for table-existence checks) are each the only one running at a time.
  The test is wrapped in `try`/`finally` so it always leaves the schema back
  at Phase 2 head, even if an assertion fails partway through.
- **CSRF mitigation is `SameSite=Lax` + an `Origin` allow-list check**, not a
  full double-submit CSRF-token scheme — considered unnecessary overhead for
  a JSON-only API with no HTML form endpoints. See ADR 0006 for the
  alternatives considered.

## Commands run
- `python3 -m py_compile` / `python3 -m compileall -q app alembic scripts` —
  zero syntax errors across every new and modified file.
- A custom AST-based cross-import checker (same technique as Phase 1's,
  written fresh for this phase) parsing every `.py` file under `app/` and
  `scripts/`, extracting every `from app.* import ...` statement, and
  confirming the imported name is genuinely defined (or is a real submodule)
  in its target file → **101/101 `app.*` import statements across 51 files
  resolved correctly** (one false positive in the checker's own submodule
  handling, the same class Phase 1's checker hit, immediately explained and
  not counted as a real issue).
- A small Python script using stdlib `tomllib` to parse `backend_v2/pyproject.toml`
  → parsed successfully; confirmed the new dependencies and `[tool.pytest.ini_options]`.
- A small Python script using `yaml.safe_load` to parse `docker-compose.yml`
  → parsed successfully; confirmed exactly `postgres`, `backend_v2`,
  `postgres_test`, `backend_v2_test` exist as services — no unplanned service
  was added.
- A small Python script using `configparser` (interpolation disabled) to
  parse `alembic.ini` → parsed successfully; confirmed `sqlalchemy.url` is
  still not present (unchanged from Phase 1).
- `grep -rniE` sweep for `print(...)`/logger calls containing
  password/token/secret-shaped content across every new module and test file
  → no unexplained plaintext credential logging found.
- `find . -iname "__pycache__" -type d -exec rm -rf {} +` — cleanup before
  packaging; confirmed empty before the final ZIP.
- Manual, line-by-line review of `app/modules/auth/service.py` (transaction
  boundaries, rollback behavior, reuse-detection logic),
  `app/modules/auth/dependencies.py` (401 vs 403 behavior, fresh-role-read),
  `app/modules/auth/router.py` (cookie attributes/path/expiry), and every
  new test file, reasoning by hand through FastAPI dependency resolution,
  SQLAlchemy async session semantics, and Alembic's online-migration
  recipe, since none of it could be executed.

## Passed checks
- `python3 -m compileall` on every new/modified `.py` file under
  `backend_v2/` — zero syntax errors.
- Custom AST cross-import checker — 101/101 resolve (see above).
- `pyproject.toml` — valid TOML; new dependencies and pytest config confirmed
  present and well-formed.
- `docker-compose.yml` — valid YAML; exactly the four expected services
  exist, no unplanned service was added.
- `alembic.ini` — valid structure; still no hardcoded `sqlalchemy.url`.
- Plaintext-secret-logging grep sweep across all new code — nothing found.
- Manual correctness review of every new module — passed, with the design
  decisions in "Architecture decisions" above chosen specifically to avoid
  known failure classes (event-loop/connection-pool scoping, nested
  `asyncio.run()`) that could not otherwise be verified by execution.

## Failed or unavailable checks in the original Claude sandbox (historical)
All of the following were **environment limitations of that sandbox**,
identical in kind to what Phase 0 and Phase 1 both hit and documented —
not a result of any assumption baked into the new code:
- `pip install fastapi` (or any real package) → **failed**: no package index
  reachable, same as Phase 0/1.
- `pytest` was unavailable in that sandbox. The dedicated Phase 2 tests
  were therefore not executed there. A later independent blocker patch did
  execute the focused non-database set; see the current verification section
  at the end of this file.
- `ruff format --check .` / `ruff check .` → **unavailable**: not installed.
- `mypy app` → **unavailable**: not installed. The codebase was written
  against the existing strict `[tool.mypy]` configuration by design, but
  that is a design intention checked by hand, not an executed, passing
  type-check.
- `alembic upgrade head` / `downgrade` / `current` → **unavailable**: alembic
  itself is not installed, and no PostgreSQL instance is reachable regardless.
  `test_migrations_phase2.py` is written to run this exact round-trip for
  real once both are available (it skips gracefully otherwise).
- `docker compose --profile test build backend_v2_test` /
  `docker compose --profile test run --rm backend_v2_test` → **unavailable**:
  Docker is not installed in this sandbox (`docker: not found`).
  `docker-compose.yml` was instead validated as structurally-correct YAML by
  hand (see "Passed checks").
- `docker compose up -d` / `curl http://localhost:8000/health/live` /
  `/health/ready` → **unavailable**: same missing-Docker limitation.

**No check above is claimed to have passed.** Where full execution wasn't
possible, the closest available static/structural verification was performed
instead and is reported separately under "Passed checks" — never conflated
with the runtime check it stands in for.

## Known risks
- - **Phase 2 has now been runtime-verified locally using Docker and PostgreSQL.**
  The authoritative quality gate completed successfully with 144 tests passed,
  Ruff format and lint checks passed, and mypy reporting no issues across
  54 source files. Ten deprecation warnings remain, but they are non-blocking.
- **Legacy secret-print status:** the current repository snapshot contains
  neither the MongoDB-URI debug print nor the teacher plaintext-password
  print. The repository owner reported rotating the exposed MongoDB
  credential; real credentials must remain external to the repository.
- **No self-registration endpoint exists** — by design, per the Phase 2
  brief; `scripts/bootstrap_admin.py` is the only way to create a user until
  Phase 3 adds admin-facing user-management endpoints on top of
  `UserRepository`.
- **No background cleanup job for expired/revoked refresh sessions** — by
  design, per the Phase 2 brief ("Do not build a background cleanup worker in
  this phase"); `refresh_sessions` will accumulate revoked/expired rows
  indefinitely until a later phase adds one.
- **Dependency version floors** (`pyjwt`, `argon2-cffi`, `email-validator`,
  the tightened `sqlalchemy>=2.0.30`) were chosen as reasonable, non-obsolete
  lower bounds; not checked against actual latest-compatible releases, since
  no package index was reachable to check against — same limitation Phase 1
  recorded for its own dependency floors.

## Pending
Everything in `docs/IMPLEMENTATION_PLAN.md` Phases 3–9 and both Milestones.
Immediately actionable items outside strict phase order:
- Keep the removed legacy credential/password debug prints from being
  reintroduced and continue keeping all real credentials outside Git.
- Run the full Docker gate (`docker compose --profile test build
  backend_v2_test && docker compose --profile test run --rm
  backend_v2_test`) in an environment with network access and/or Docker, and
  record real (not static-only) pass/fail counts for pytest/Ruff/mypy.
- Run `docker compose up -d`, `alembic upgrade head`, and the two health
  endpoints in that same environment.

## Next phase
Phase 3: academic domain models and management APIs (classrooms, subjects,
teachers, students, timetable, announcements), built directly on this
phase's `require_roles`/`get_current_active_user` dependencies — see
`docs/IMPLEMENTATION_PLAN.md` Phase 3.


# Independent Phase 2 runtime-blocker patch

## Completed
- Removed invalid SQLAlchemy dataclass-only `repr=False` arguments from the
  `User.password_hash` and `RefreshSession.token_hash` mapped columns; their
  explicit safe `__repr__` methods still exclude sensitive hashes.
- Made `UserRole` a `StrEnum` and configured SQLAlchemy `Enum` with
  `values_callable`, so PostgreSQL stores `admin`/`teacher`/`student` exactly
  as migration `6eeb9420bf8b` defines them.
- Added `app/db/models.py` and imported its models in `alembic/env.py`, so
  `Base.metadata` contains both Phase 2 tables before Alembic autogenerate.
- Added `SELECT ... FOR UPDATE` support to refresh-session lookup and use it
  during refresh rotation, preventing two concurrent requests from consuming
  the same active refresh token.
- Isolated production Settings tests from the Docker test environment's
  insecure localhost-cookie override; added direct production-cookie, token
  lifetime, and JWT-algorithm validation tests.
- Converted database-backed auth HTTP tests from synchronous `TestClient` to
  `httpx.AsyncClient` + `ASGITransport` so FastAPI and async SQLAlchemy use the
  same event loop.
- Added model-import/metadata regression tests and a repository row-lock test.
- Confirmed the current repository contains neither the old MongoDB URI debug
  print nor the teacher plaintext-password print; credential rotation was
  reported completed by the repository owner.

## Verification actually performed
- `python -m compileall -q app alembic scripts` — passed.
- Real imports of `User` and `RefreshSession` — passed without SQLAlchemy
  dataclass-mapping errors.
- Runtime metadata assertion — `users` and `refresh_sessions` registered.
- Runtime enum assertion — ORM enum values are exactly
  `admin`, `teacher`, `student`.
- Selected non-database pytest set (configuration, password/JWT security,
  model registration, row-lock query, integrity mapping, error envelope, and
  liveness coverage) — **67 passed**.
- Current suite source contains 125 test functions across 17 files; pytest
  collection expands parameterized cases to 144 test items.
- TOML, YAML, INI, and Python AST structural parsing — passed.

## Local authoritative verification completed
- `docker compose --profile test build backend_v2_test` — passed.
- `docker compose --profile test run --rm backend_v2_test` — passed.
- PostgreSQL test service reached healthy status.
- Alembic applied the Phase 1 baseline revision `98161483914f`.
- Alembic applied the Phase 2 revision `6eeb9420bf8b`.
- Pytest collected 144 test items.
- **144 tests passed**.
- Ruff format check passed — **60 files already formatted**.
- Ruff lint check passed — **All checks passed**.
- mypy passed — **no issues found in 54 source files**.
- 10 non-blocking deprecation warnings remain:
  - 1 Starlette/TestClient warning.
  - 9 HTTPX per-request-cookie warnings.

## Phase 2 completion summary
- PostgreSQL-backed User model.
- Admin, teacher, and student roles.
- Argon2id password hashing.
- JWT access tokens.
- Opaque hashed refresh-token sessions.
- Refresh-token rotation, revocation, reuse detection, and row locking.
- Login, refresh, logout, and `/me` endpoints.
- Database-driven RBAC.
- Secure HttpOnly refresh-cookie flow.
- Alembic migration `6eeb9420bf8b`.
- Admin bootstrap script.
- Reproducible Docker/PostgreSQL quality gate.
- 144-test passing suite.

## Pending
- Run the normal application stack and verify `/health/live` and `/health/ready`
  after any future environment or deployment configuration change.
- Address the non-blocking Starlette and HTTPX deprecation warnings in a later
  dependency-maintenance pass.
- Continue with Phase 3.

## Blockers
- None.

## Next phase
Phase 3: academic domain models and management APIs.

# Phase 3 Stage 1: Academic Domain, Profiles, Announcements

## Status
**In progress — Stage 1 only, not complete.** This section covers a
checkpoint continuation of Stage 1: the `academics` and `profiles`
modules arrived already implemented in the checkpoint this session
started from and were inspected/verified, not rewritten; this session's
own new work is the `announcements` module, full Phase 3 model
registration, the single Phase 3 Alembic migration, test-database
cleanup ordering, and the Stage 1 test suite described below. **Phase 3
Stage 2 (services layer, API routers) and Phase 4 have not been
started.** See `docs/HANDOVER_PHASE_3_STAGE_1.md` for the full handover.

## Completed this checkpoint
1. Inspected the incoming `academics` and `profiles` modules
   (`app/modules/academics/{models,errors,schemas,repository,normalization}.py`,
   `app/modules/profiles/{models,errors,repository}.py`) against
   `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md` Phase 2/3, and
   `docs/adr/0006-...`: UUID primary keys, `created_at`/`updated_at`
   timestamps, FK `ondelete` behavior, uniqueness constraints, indexes,
   no duplicated credential fields, no comma-separated relationship IDs,
   repository transaction ownership (caller commits, repository only
   flushes), and safe domain-error mapping were all already correct — no
   genuine defect was found, so neither module was rewritten, per this
   checkpoint's explicit instruction.
2. Implemented `app/modules/announcements/` from scratch: `models.py`
   (`Announcement`, `AnnouncementAudience` enum, and the explicit
   `AnnouncementClassroom` many-to-many association table — not a
   comma-separated ID list), `errors.py`, `schemas.py`
   (`AnnouncementCreate`/`AnnouncementUpdate`/`AnnouncementRead`, with
   audience/classroom_ids consistency validated at the schema layer),
   and `repository.py` (author-existence, audience-consistency, and
   classroom-reference validation, all performed before any row is
   inserted).
3. Updated `app/db/models.py` to import and re-export every Phase 2 +
   Phase 3 model (`User`, `RefreshSession`, `Classroom`, `Subject`,
   `TeacherProfile`, `StudentProfile`, `TeacherAssignment`,
   `TimetableEntry`, `Announcement`, `AnnouncementClassroom`).
4. Updated `alembic/env.py` to import the same Phase 3 models so
   `target_metadata` (`Base.metadata`) contains all eight new tables in
   addition to Phase 2's two.
5. Added exactly one new Alembic migration,
   `alembic/versions/20260730_1200_32819e0a6027_create_academics_profiles_announcements.py`
   (revision `32819e0a6027`, `down_revision = "6eeb9420bf8b"` — Phase 2
   head). Creates, in FK-dependency order: `classrooms`, `subjects`,
   `teacher_profiles`, `student_profiles`, `teacher_assignments`,
   `timetable_entries` (plus the `day_of_week` enum), `announcements`
   (plus the `announcement_audience` enum), `announcement_classrooms`.
   `downgrade()` reverses this exactly, dropping both new enum types
   only after every table using them is gone, landing back at Phase 2
   head with no leftover type. Constraint/index names are written out
   to match each model's `__table_args__` exactly (verified by direct
   comparison against every model file, not assumed).
6. Extended `app/tests/conftest.py`'s `db_session` per-test cleanup:
   replaced the Phase-2-only two-table `DELETE` with an explicit,
   child-before-parent ordered list covering all ten Phase 2 + Phase 3
   tables (`announcement_classrooms` → `announcements` →
   `timetable_entries` → `teacher_assignments` → `student_profiles` →
   `teacher_profiles` → `subjects` → `classrooms` → `refresh_sessions`
   → `users`), so every database-backed test still starts from an
   empty, fully-migrated schema.
7. Added five new test files (see "Tests added" below).

## Models added this checkpoint
- `app.modules.announcements.models.Announcement` — `announcements` table.
- `app.modules.announcements.models.AnnouncementAudience` — native
  `announcement_audience` enum (`all` / `classroom`).
- `app.modules.announcements.models.AnnouncementClassroom` —
  `announcement_classrooms` explicit many-to-many association table.

(`Classroom`, `Subject`, `TeacherAssignment`, `TimetableEntry`,
`TeacherProfile`, `StudentProfile` arrived already implemented in the
incoming checkpoint and were verified, not recreated — see
`docs/HANDOVER_PHASE_3_STAGE_1.md` for the review notes.)

## Migration added this checkpoint
- `32819e0a6027` — `create_academics_profiles_announcements`, parent
  `6eeb9420bf8b` (Phase 2 head). Exactly one migration, as required.

## Tests added this checkpoint
- `app/tests/test_phase3_model_registration.py` — every Phase 3 model
  imports cleanly and is registered in `Base.metadata`; Phase 2 tables
  still coexist.
- `app/tests/test_academics_repository.py` — classroom/subject
  creation + code normalization + duplicate-code rejection; teacher
  assignment creation, duplicate-assignment rejection, missing-related-
  record rejection; timetable creation and both collision rules
  (same classroom same slot, same teacher same slot across
  classrooms); timetable missing-related-record rejection.
- `app/tests/test_profiles_repository.py` — one teacher profile per
  teacher user, one student profile per student user, role-mismatch
  rejection for both, missing-user rejection for both, student
  classroom-membership assignment + lookup, duplicate classroom/roll-
  number rejection.
- `app/tests/test_announcements_repository.py` — schema-level audience/
  classroom_ids consistency validation (both directions) and
  deduplication; repository-level create for both audiences, full
  round trip via `AnnouncementRead.from_model`, missing-author
  rejection, missing-classroom rejection, repository-level audience
  re-validation (bypassing the schema), deactivation.
- `app/tests/test_migrations_phase3.py` — upgrade to Phase 3 Stage 1
  head, downgrade to Phase 2 head (`6eeb9420bf8b`, not the Phase 1
  baseline — this migration's actual parent), re-upgrade; asserts every
  new table's presence/absence at each step and that Phase 2's own
  tables are untouched by the downgrade.

All of the above are **database-backed** and use the existing
`db_session` fixture, which skips gracefully (not a failure) when no
reachable PostgreSQL test instance exists — same pattern as every
Phase 2 database-backed test. The four schema-only `AnnouncementCreate`
validation tests need no database and always run.

## Verification actually performed this checkpoint
- `python3 -m compileall -q app alembic scripts` — **passed**, zero
  syntax errors across the full tree (existing files + everything added
  this checkpoint).
- A custom AST-based cross-import checker (every `from app.* import
  name` in `app/` and `alembic/`, confirming `name` is genuinely defined
  in its target module) — **277/277 internal imports resolve
  correctly**.
- Manual line-length check against the project's `ruff` config
  (`line-length = 100`) across every file touched or added this
  checkpoint — two over-length lines found and fixed.
- Manual, file-by-file review of `academics`/`profiles` models,
  repositories, and errors against the Stage 1 review checklist (UUID
  PKs, timestamps, FK `ondelete`, uniqueness, indexes, no duplicated
  credential fields, no comma-separated IDs, repository transaction
  ownership, safe error mapping) — no defect found, nothing changed.
- Manual review of the new migration file against every Stage 1 model's
  `__table_args__`, column-by-column and constraint-by-constraint, to
  confirm the hand-written migration matches the ORM models exactly
  (this environment cannot run `alembic revision --autogenerate` — see
  "Not verified" below).

## Not verified this checkpoint (sandbox has no network egress, no
Docker, and no installed Python dependencies — confirmed empirically,
not assumed; identical limitation to every prior phase in this
rebuild)
- `pytest` was **not run**. None of the new or existing Phase 2/3 tests
  have been executed in this environment.
- `alembic upgrade head` / `downgrade` / re-`upgrade` against a real
  PostgreSQL instance was **not run**. The migration's correctness is
  based on manual review only, not an executed round-trip.
- `ruff format --check .` and `ruff check .` were **not run** (`ruff`
  is not installed and cannot be installed — no network egress).
- `mypy app` was **not run** (`mypy` is not installed and cannot be
  installed).
- `docker compose --profile test build backend_v2_test` /
  `docker compose --profile test run --rm backend_v2_test` were **not
  run** (Docker is not installed in this sandbox).

**No check above is claimed to have passed if it did not actually run.**
The repository owner should run the full Docker gate
(`docker compose --profile test build backend_v2_test && docker compose
--profile test run --rm backend_v2_test`) before trusting this
checkpoint's runtime behavior, exactly as flagged after every prior
phase in this rebuild.

## Pending — Stage 1
- Real (Docker/PostgreSQL) execution of the full Stage 1 test suite and
  the migration round-trip, per "Not verified" above.
- `ruff format --check .`, `ruff check .`, and `mypy app` in an
  environment where those tools are installable.

## Pending — Stage 2 and beyond (not started, out of this
checkpoint's scope)
- Service-layer orchestration and FastAPI routers for academics,
  profiles, and announcements (Stage 2, per this checkpoint's explicit
  instruction not to implement API routes).
- Phase 4 (attendance core) and every phase after it, unchanged from
  `docs/IMPLEMENTATION_PLAN.md`.

## Next phase
Phase 3 Stage 2: service-layer orchestration and API routers for
academics, profiles, and announcements, building directly on the
repositories delivered in Stage 1 — see `docs/IMPLEMENTATION_PLAN.md`
Phase 3 and `docs/HANDOVER_PHASE_3_STAGE_1.md`.

# Phase 3 Stage 2: Services, APIs, and Object Authorization

## Status

**Implementation completed; Docker/PostgreSQL verification pending.** This
checkpoint implements Stage 2 only. It does not mark Phase 3 complete, does
not claim Stage 1's migration is runtime-verified, and does not begin Phase 3
final integration or Phase 4.

## Completed

1. Added focused async services and separate routers for classrooms,
   subjects, teacher profiles, student profiles, teacher assignments,
   student classroom membership, timetable entries, and announcements.
2. Added `service_transaction`, which commits after a complete operation and
   rolls back any unfinished transaction in `finally` without a broad
   exception catch.
3. Mounted every Stage 2 router through `app/api/router.py` under `/api/v1`.
4. Reused Phase 2's `get_current_user`, `get_current_active_user`, and
   `require_roles`; no second authentication or RBAC system was introduced.
5. Added reusable object-authorization helpers. Wrong-role access is `403`;
   an allowed role requesting another user's private or unrelated resource
   receives that resource's normal `404`.
6. Added paginated admin management APIs and soft-deactivation operations for
   every Stage 1 aggregate, plus teacher-assignment and student-membership
   operations.
7. Derived teacher/student access from current PostgreSQL state: current user,
   active role-linked profile, active assignments, and current classroom
   membership.
8. Required timetable writes to match an active teacher/classroom/subject
   assignment and preserved Stage 1 collision errors as stable `409`
   responses.
9. Extended the existing announcement audience enum with `teacher` and
   `student` to satisfy Stage 2's explicit role-audience acceptance criteria.
   The still-unverified Stage 1 migration remains revision `32819e0a6027`;
   ADR 0008 records why it was extended before its pending gate.
10. Added PostgreSQL HTTP integration coverage for authentication/RBAC,
    admin CRUD/conflicts/pagination/deactivation, teacher/student scope,
    timetable assignment/collision behavior, announcement visibility, the
    standard error envelope, and request-ID propagation.
11. Updated `backend_v2/README.md`, created
    `docs/HANDOVER_PHASE_3_STAGE_2.md`, and added ADR 0008.

## Files created

- `backend_v2/app/db/transaction.py`
- `backend_v2/app/schemas/pagination.py`
- `backend_v2/app/modules/auth/authorization.py`
- `backend_v2/app/modules/academics/assignments_service.py`
- `backend_v2/app/modules/academics/classrooms_service.py`
- `backend_v2/app/modules/academics/subjects_service.py`
- `backend_v2/app/modules/academics/timetable_service.py`
- `backend_v2/app/modules/academics/assignments_router.py`
- `backend_v2/app/modules/academics/classrooms_router.py`
- `backend_v2/app/modules/academics/subjects_router.py`
- `backend_v2/app/modules/academics/timetable_router.py`
- `backend_v2/app/modules/profiles/teacher_service.py`
- `backend_v2/app/modules/profiles/student_service.py`
- `backend_v2/app/modules/profiles/membership_service.py`
- `backend_v2/app/modules/profiles/teacher_router.py`
- `backend_v2/app/modules/profiles/student_router.py`
- `backend_v2/app/modules/announcements/service.py`
- `backend_v2/app/modules/announcements/router.py`
- `backend_v2/app/tests/phase3_http_helpers.py`
- `backend_v2/app/tests/test_phase3_admin_http.py`
- `backend_v2/app/tests/test_phase3_scoped_access_http.py`
- `backend_v2/app/tests/test_phase3_announcements_timetable_http.py`
- `backend_v2/app/tests/test_service_transaction.py`
- `docs/adr/0008-phase3-stage2-services-and-authorization.md`
- `docs/HANDOVER_PHASE_3_STAGE_2.md`

## Files modified

- `backend_v2/app/api/router.py`
- `backend_v2/app/main.py`
- `backend_v2/app/modules/academics/__init__.py`
- `backend_v2/app/modules/academics/errors.py`
- `backend_v2/app/modules/academics/repository.py`
- `backend_v2/app/modules/academics/schemas.py`
- `backend_v2/app/modules/announcements/__init__.py`
- `backend_v2/app/modules/announcements/errors.py`
- `backend_v2/app/modules/announcements/models.py`
- `backend_v2/app/modules/announcements/repository.py`
- `backend_v2/app/modules/announcements/schemas.py`
- `backend_v2/app/modules/profiles/errors.py`
- `backend_v2/app/modules/profiles/repository.py`
- `backend_v2/app/modules/profiles/schemas.py`
- `backend_v2/app/tests/conftest.py`
- `backend_v2/app/tests/test_phase3_model_registration.py`
- `backend_v2/alembic/versions/20260730_1200_32819e0a6027_create_academics_profiles_announcements.py`
- `backend_v2/pyproject.toml`
- `backend_v2/README.md`
- `docs/adr/0007-phase3-stage1-academic-domain.md`
- `docs/PROGRESS.md`

## Checks actually executed

- Windows command discovery for `python`, `python3`, `ruff`, `mypy`, and
  `pytest`: none was available.
- `py -3.12 -m compileall -q app alembic scripts`: attempted; the launcher
  reported `No installed Python found`, so this did not run and is not a
  passing compile check.
- `py -3.12 -c "import app.main"`: attempted; blocked by the same missing
  Python installation and not claimed as passed.
- WSL `python3 --version`: first denied by sandbox isolation, then retried
  with approval; WSL reported `python3: not found`.
- Node-based delimiter/string structural scan over all 104 Python files:
  passed.
- Node-based internal `app.*` import structural scan: 498 imported names
  resolved.
- Repository-wide Python line-length scan against Ruff's configured maximum:
  all lines are at most 100 characters.
- Stage 2 placeholder/broad-catch scan: no TODO/FIXME/NotImplemented,
  `pass`, fake assertion, or broad exception catch in Stage 2 files.
- Test inventory: 173 test functions across 26 test files; this is a source
  count, not a pytest execution result.
- Router registration/decorator inventory: all seven Stage 2 resource routers
  are mounted alongside the existing auth router and expose the documented
  methods.

## Not executed

- Docker, by explicit task restriction.
- PostgreSQL migration upgrade/downgrade/re-upgrade.
- pytest, Ruff format/lint, and mypy because the executables and a local
  Python installation are unavailable.

No unavailable check is claimed as passed.

## Pending

- Run the authoritative Docker/PostgreSQL gate from
  `docs/HANDOVER_PHASE_3_STAGE_2.md`.
- Fix any runtime, Ruff, or mypy failure that gate exposes.
- Complete Phase 3 final integration separately; do not begin it
  automatically from this checkpoint.

## Blockers

Implementation has no known blocker. Runtime verification is blocked by the
current task restriction (no Docker) and the absence of a local Python
toolchain.

---

# Phase 3 Closure — Final Integration, Bulk Import, and Documentation

**Status: Phase 3 implementation complete and authoritatively verified with
Docker and PostgreSQL.** The final local gate completed on 2026-07-30 with
213 tests passing, Ruff format and lint passing, and mypy reporting zero
issues across 106 source files. This section is the final Phase 3 record;
`docs/HANDOVER_PHASE_3.md` contains the detailed handover.

## Stage 1 summary

Academic domain (`classrooms`, `subjects`, `teacher_assignments`,
`timetable_entries`), profiles (`teacher_profiles`, `student_profiles`),
and announcements (`announcements`, `announcement_classrooms`) delivered as
ORM models, repositories, one Alembic migration (`32819e0a6027`, parent
`6eeb9420bf8b`), and database-backed tests. ADR 0007. See
`docs/HANDOVER_PHASE_3_STAGE_1.md`.

## Stage 2 summary

Service-owned transaction boundaries, seven modular routers, admin CRUD,
teacher/student object-level authorization, announcement visibility, HTTP
integration tests, ADR 0008. See `docs/HANDOVER_PHASE_3_STAGE_2.md`.

## Bulk-import summary

`app/modules/bulk_imports/` — admin-only, bounded (2 MiB / 500 non-blank
rows) CSV/XLSX import for `classrooms`, `subjects`, `teacher-profiles`,
`student-profiles`. Per-row independent commit/rollback via the shared
`service_transaction` helper; no filesystem writes; XLSX read with
`data_only=True` (no formula evaluation); error responses carry only a
stable code + safe message, never the submitted row or any password/
token/hash field. ADR 0009.

## Final-integration fixes (this closure session)

One genuine bug found and fixed:

- **`app/modules/bulk_imports/parser.py`**: `_normalized_row()` did not
  normalize XLSX `int`/`float`/`bool` cell values before Pydantic
  validation, so a numeric-looking identifier column (classroom/subject
  `code`, `employee_code`, `roll_number`) typed as a plain number in Excel
  — a very common real case — would spuriously fail row validation
  (Pydantic v2's lax `str` mode does not coerce `int`/`float`). Fixed with
  a new `_normalized_scalar()` helper: `int` -> plain decimal string;
  whole-number `float` -> string with no trailing `.0`; other finite
  `float` -> clean decimal string; `NaN`/infinite `float` -> rejected
  (`BulkImportFileError`); `bool` left as a native bool; anything else
  passed through unchanged (deliberately narrow, no broad object
  coercion). Verified against the installed `openpyxl` that whole-number
  floats round-trip as `int`, non-whole floats as `float`, and — notably —
  `NaN`/infinity cannot round-trip through openpyxl's own writer at all
  (silently becomes an empty cell / `None`), so that rejection path is
  tested directly against the helper rather than via a real workbook.

No other genuine correctness, security, or consistency issue was found in
this closure session's review of the previously-unreviewed routers
(student-profile, timetable, subjects, assignments, announcements) — see
`docs/HANDOVER_PHASE_3.md` §4.3 for what was checked.

## Migration revision

`32819e0a6027`, parent `6eeb9420bf8b`.

The Docker/PostgreSQL gate successfully upgraded through the complete
migration chain. The Phase 3 migration round-trip test also passed:
upgrade to head, downgrade to `6eeb9420bf8b`, and re-upgrade to head.

Revision `32819e0a6027` is now verified and immutable. Future schema changes
must use a new Alembic revision.

## Route/endpoint summary

Nine router files (`auth`, `classrooms`, `subjects`, `teacher-profiles`,
`student-profiles`, `teacher-assignments`, `timetable-entries`,
`announcements`, `bulk_imports`), 43 unique `(method, path)` route
registrations, zero duplicates (AST-scanned this session). Full inventory
in `backend_v2/README.md`.

## Total test inventory

The authoritative Docker pytest run collected **213 test items**.

Final result:

- **213 passed**
- **0 failed**
- **10 non-blocking deprecation warnings**

This includes repository, migration, authentication, RBAC, scoped-access,
announcement, timetable, profile, service-transaction, bulk-import parser,
CSV, and XLSX integration coverage.

## Checks actually run (this closure session)

- `python -m compileall -q app alembic scripts` — passed, 0 syntax errors.
- Custom AST-based internal `app.*` import-resolution scan — 106/106
  files, 0 unresolved imports.
- Model-registration / migration-table-name diff — 8/8 tables match.
- Duplicate route `(method, path)` scan across all 9 router files — 43
  unique, 0 duplicates.
- Trailing-whitespace scan — 0 matches. Line-length scan (100-char Ruff
  config) — 0 lines over.
- Broad-exception scan — only the 3 pre-existing, legitimate Phase 1/2
  occurrences; 0 in Phase 3 code.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan — 0 matches.
- Secret/debug-print scan + repo-wide real-`.env` search — 0 matches.
- `pyproject.toml` (tomllib), `alembic.ini` (configparser), and
  `docker-compose.yml` (yaml) structural parsing — all valid; confirmed
  `openpyxl`/`python-multipart` are in `project.dependencies` (not just
  `dev`), no hardcoded `sqlalchemy.url`, exactly the 4 expected Compose
  services.
- Direct `openpyxl` (3.1.5, present in this sandbox) round-trip probing of
  the exact numeric/bool/NaN/infinity cases the parser fix depends on.

## Checks unavailable in the closure sandbox — historical

These limitations applied only to the closure sandbox. All relevant
runtime and quality checks were subsequently completed locally with Docker
and PostgreSQL, as recorded below.

## Authoritative Docker/PostgreSQL verification completed

Completed locally on 2026-07-30:

- `backend_v2_test` Docker image built successfully.
- PostgreSQL test service started and became healthy.
- Alembic upgraded through revision `32819e0a6027`.
- Phase 2 and Phase 3 migration round-trip tests passed.
- Pytest: **213 passed, 0 failed, 10 warnings**.
- Ruff format: **113 files already formatted**.
- Ruff lint: **All checks passed**.
- Mypy: **Success: no issues found in 106 source files**.

## Blockers before Phase 4

No Phase 3 implementation or verification blocker remains.

The 10 warnings are non-blocking dependency/test-client deprecation
warnings and may be addressed during a later maintenance pass. Historical
legacy security or deployment decisions remain separate from Phase 4 and
must not be confused with Phase 3 gate failures.

## Next phase

Phase 4: Attendance core and audit trail.

Phase 4 is ready to begin from the verified Phase 3 baseline. Start with
the Phase 4 scope in `docs/IMPLEMENTATION_PLAN.md` and the exact starting
point in `docs/HANDOVER_PHASE_3.md` §19. No Phase 4 implementation has been
started yet.

---

# Phase 4, Stage 1 (Attendance + audit-log foundation)

**Status: in progress, not complete.** See `docs/HANDOVER_PHASE_4_STAGE_1.md`
for the full write-up; summarized here.

## What was delivered this session

- `app/modules/attendance/` (models, errors, schemas, repository) built
  from scratch: `AttendanceRecord` (status enum `present`/`absent`, unique
  on student+classroom+subject+date) and `AuditLog` (outcome enum
  `success`/`blocked`, append-only, sanitized JSONB `event_metadata`).
- `app/db/models.py` and `alembic/env.py` updated to register both new
  models alongside every Phase 2/3 model.
- One new Alembic migration, `e1208296dad5`, parented on Phase 3 head
  (`32819e0a6027`, untouched and unedited).
- `app/tests/conftest.py`'s per-test cleanup list extended to
  `attendance_records`/`audit_logs` (child-first).
- Five new test files: `test_phase4_model_registration.py`,
  `test_migrations_phase4.py`, `test_attendance_repository.py`,
  `test_audit_log_repository.py` (including a structural regression test
  asserting `AuditLogRepository` has no update/delete method).
- `docs/adr/0010-phase4-attendance-and-audit-trail.md` (Stage 1 decisions
  only) and `docs/HANDOVER_PHASE_4_STAGE_1.md`.

## Explicitly out of scope this session

No service layer, no authorization/ownership checks, no FastAPI routers,
no CSV export, no blocked-audit-logging behavior, no stats/detail/daily
endpoints. Nothing in `app/modules/attendance/` is reachable over HTTP
yet — see `docs/HANDOVER_PHASE_4_STAGE_1.md` for the full "explicitly out
of scope" list.

## Migration revision

`e1208296dad5`, parent `32819e0a6027` (Phase 3 head, immutable).

Not runtime-verified in this sandbox (no Docker, no reachable PostgreSQL,
no installed `sqlalchemy`/`alembic`/`fastapi`/`pytest` — confirmed
empirically, the same limitation recorded throughout every Phase 3
checkpoint in this sandbox). Verified only by manual column-by-column
comparison against the ORM models plus the static scans below.

## Checks actually run this session

- `python -m compileall -q app alembic scripts` — passed, 0 syntax
  errors across the whole tree.
- Custom AST-based internal `app.*` import-resolution scan — 353/354
  resolved; the one flagged case is a known, pre-existing false-positive
  class (submodule import, not a package-level name) already documented
  in Phase 3's own closure session, unrelated to this session's changes.
- Model-registration / migration-table-name diff across all three
  migration files — 12/12 tables match exactly in both directions.
- Constraint/index/FK/PK name diff between `app/modules/attendance/models.py`
  and the new migration — every name matches, either literally or via
  `app/db/naming.py`'s shared naming convention.
- Trailing-whitespace scan — 0 matches. Line-length scan (100-char Ruff
  config) — 0 lines over (one file needed a wrap during authoring; fixed
  and re-verified).
- Broad-exception scan — 0 matches in the new module.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan — 0 matches.
- Secret/debug-print scan — 0 matches.

## Checks unavailable in this sandbox — same historical limitation

`pip install` of any package (fastapi, sqlalchemy, alembic, pytest,
etc.), `ruff`, `mypy`, and Docker are all unavailable in this sandbox, for
the exact same reasons recorded in every Phase 3 checkpoint. No check
above is claimed to have passed where it did not actually run.

## Next task

Phase 4 Stage 2: `AttendanceService`/`AuditLogService` transaction
orchestration, authorization/ownership checks (teacher-assignment-based,
student self-service), the blocked-audit-logging design outlined in ADR
0010's "Consequences" section, FastAPI routers, statistics, and CSV
export — see `docs/IMPLEMENTATION_PLAN.md` Phase 4's full acceptance
criteria (unchanged by this Stage 1 checkpoint) and
`docs/HANDOVER_PHASE_4_STAGE_1.md`'s "Recommended next task."

---

# Phase 4, Stage 2 (Attendance service, authorization, audit logging)

**Status: complete for its own defined scope.** See
`docs/HANDOVER_PHASE_4_STAGE_2.md` for the full write-up; summarized
here.

## What was delivered this session

- `app/modules/attendance/service.py` built from scratch:
  `AttendanceService.bulk_save` (one transaction covering reference
  lookup, admin/teacher authorization, active-reference checks, student
  validation, the create/update upsert loop, and the success-audit
  write) and `BlockedAuditWriter` (an independent `AsyncSession`, off the
  shared cached engine, that persists exactly one blocked-attempt audit
  row before the concealed ownership error is raised).
- `app/modules/attendance/errors.py` extended with seven Stage 2 errors
  (batch-too-large, duplicate-student-in-batch, role-not-permitted,
  the concealed scope-not-found error, and three student-validation
  errors) — Stage 1's errors untouched.
- `app/modules/attendance/schemas.py` extended with
  `AttendanceBulkSaveResult` (counts + record IDs only — the batch is
  never echoed back).
- `app/tests/test_attendance_service.py`: 24 new database-backed
  service-level tests, covering admin/teacher success paths, concealed
  ownership denial and its blocked-audit side effect, every
  active/inactive reference combination, duplicate/oversized-batch
  defense-in-depth (via `model_construct` to bypass schema validation
  and genuinely exercise the service-level check), create-vs-update
  upsert semantics, `marked_by_user_id` provenance, and four distinct
  rollback/atomicity scenarios (forced repository failure, invalid later
  student, failed success-audit write, and the "exactly one success
  audit" positive case).
- `docs/HANDOVER_PHASE_4_STAGE_2.md` and a Stage 2 addendum to ADR 0010
  (Stage 1's decisions unedited).

## Genuine issues found and fixed during this session's own review

1. A blocked-audit-write failure could have propagated its own exception
   in place of the intended `AttendanceScopeNotFoundError`, silently
   changing the client-visible error depending on an unrelated write's
   success. Fixed with a narrow, documented `try/except Exception`
   (logging only the exception type, never its message) around the
   `BlockedAuditWriter.write(...)` call — the concealed error is always
   raised afterward regardless.
2. A bare `assert classroom is not None` / `assert subject is not None`
   guarding a genuine post-authorization invariant would silently
   disappear under `python -O`. Replaced with an explicit `if ... is
   None: raise RuntimeError(...)` check.

## Explicitly out of scope this session

No FastAPI routers, no CSV export, no statistics/detail/daily endpoints,
no student self-service. Nothing in `app/modules/attendance/` is
reachable over HTTP yet — see `docs/HANDOVER_PHASE_4_STAGE_2.md`'s
"Must NOT be redone" / "Exact Stage 3 starting point" for the full list.

## Checks actually run this session

- `python -m compileall -q app alembic scripts` — passed, 0 syntax
  errors across the whole tree, including every new/modified file.
- Custom AST-based internal `app.*` import-resolution scan — 389/389
  `app.*` imports resolved to an existing module across the whole tree.
- A second, stricter AST scan for this session's new/modified files
  specifically: every individual imported *name* (not just the module)
  checked against that module's actual top-level definitions — 0
  problems.
- Model-registration / migration-table-name diff — 12/12 tables still
  match exactly (Stage 2 adds no new tables; unchanged-invariant check).
- Trailing-whitespace scan — 0 matches. Line-length scan (100-char Ruff
  config) — 0 lines over, after wrapping 19 lines in the new test file
  during authoring.
- Broad-exception scan — **1 match**, the single deliberate, documented
  `except Exception` described above (mirrors the one already-accepted
  instance of this idiom in `app/db/session.py`). Reported honestly, not
  as zero.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan — 0 matches.
- Secret/debug-print scan — 0 genuine matches (the test-only `_PASSWORD`
  constant and a deliberate `"TOP-SECRET-REMARK-VALUE"` test literal used
  specifically to prove it does *not* leak into audit metadata are both
  expected and reviewed, not real secrets).

## Checks unavailable in this sandbox — same historical limitation

`pip install` of any package, `ruff`, `mypy`, and Docker are all
unavailable in this sandbox, for the exact same reasons recorded in
every Phase 3/4 checkpoint. As a direct consequence, the 24 new tests
were never collected or run by `pytest` in this session — they are
syntactically valid and structurally consistent with the already-passing
Stage 1 fixture conventions, but not runtime-verified here. No check
above is claimed to have passed where it did not actually run.

## Next task

Phase 4 Stage 3: FastAPI routers for bulk-mark (admin + teacher) and
audit-log reads (admin-only); statistics/detail/daily endpoints built on
`AttendanceRepository.aggregate_counts` (delivered in Stage 1, unused
until now); CSV export; student self-service
(`/attendance/mystats`-equivalent); and threading a router-level
`request_id` (from `request.state.request_id`, already set by existing
middleware) into `AttendanceService.bulk_save`'s existing `request_id`
parameter — see `docs/HANDOVER_PHASE_4_STAGE_2.md`'s "Exact Stage 3
starting point" and `docs/IMPLEMENTATION_PLAN.md` Phase 4's full
acceptance criteria (unchanged by this Stage 2 checkpoint).

## Phase 4 Stage 3 — attendance reads, statistics, CSV export, audit-log API

Built on Stage 1 (models/repositories/migration `e1208296dad5`, all
unmodified) and Stage 2 (`AttendanceService.bulk_save`,
`BlockedAuditWriter`, unmodified). Full detail in
`docs/HANDOVER_PHASE_4_STAGE_3.md` — this is a summary.

### What was added

- `AttendanceRepository` extended: `status` filter added to
  `list`/`count`/`aggregate_counts`; new `list_daily`,
  `aggregate_by_student`, `aggregate_by_classroom`, `list_for_export`
  (three new typed dataclasses, never a raw SQLAlchemy `Row`).
- `AttendanceReadService` (new `read_service.py`): one shared
  `authorize_scope` method reused by every general read/export
  endpoint, mirroring Stage 2's write-scope authorization exactly
  (concealed teacher denial, active-classroom/subject admin check).
- `POST /attendance/bulk`, `GET /attendance/{detail,daily,stats,export}`,
  `GET /attendance/me/{detail,stats}` — new `router.py`.
- `GET /audit-logs`, `GET /audit-logs/{id}` — new `audit_router.py`,
  admin-only, read-only, calling `AuditLogRepository` directly.
- Both routers registered exactly once in `app/api/router.py`.
- In-memory CSV export (`csv_export.py`): stable column order, UTF-8,
  no temporary file, server-controlled filename, apostrophe-prefix
  formula-injection escaping for cells beginning with `=`/`+`/`-`/`@`.
- Student self-service: `AttendanceReadService._resolve_own_student_profile`
  derives the caller's `StudentProfile` from `current_user.id`; no
  `student_profile_id` parameter exists on either `/me/*` route.
- Statistics: `overall`/`student`/`classroom` grouping, each one SQL
  `GROUP BY ... FILTER (WHERE ...)` aggregation; zero records →
  `attendance_percentage = 0.0`; otherwise rounded to 2 decimal places;
  `present_count + absent_count == total_count` always.
- Four new HTTP test files: `test_attendance_http.py`,
  `test_attendance_stats_http.py`, `test_attendance_csv_http.py`,
  `test_audit_log_http.py` — real router → service → repository →
  Postgres path, not mocked.

### Checks actually run

`python -m compileall` (0 errors), AST import-resolution scan (110/110
resolved), duplicate-route scan (0 duplicates across 55 total routes),
repository/service/router signature-consistency scan, migration/model
sanity check (four revision files unchanged, `e1208296dad5`
byte-for-byte untouched), line-length scan (0 over 100 chars after
fixes), trailing-whitespace scan (0 matches), broad-exception scan (1
documented match, mirroring Stage 2's accepted pattern), TODO/fake-
assertion scan (0 matches), secret/debug-print scan (0 matches).

### Pending

`pytest` is not installed in this sandbox (confirmed:
`ModuleNotFoundError`) and there is no network egress to install it.
Docker, Ruff, and mypy are unavailable for the same reason as every
prior phase. **None of Stage 3's four new HTTP test files have been
collected or run by pytest** — they are syntactically valid and
structurally consistent with the passing Stage 1/2 conventions, but not
runtime-verified. No claim above states these checks passed where they
did not run.

No Git commit, branch, tag, or stash was created or modified this
session.

### Next task

Phase 4 Stage 4: final integration. Run the Docker test gate (`alembic
upgrade head` through `e1208296dad5`, then the full `pytest` suite
including all four new Stage 3 files), run `ruff format --check` /
`ruff check` / `mypy app` and fix any genuine finding, re-verify AUDIT.md
C4 now has passing (not just written) test coverage, then write the
consolidated `docs/HANDOVER_PHASE_4.md`. Phase 5 (face recognition, ADR
0005) remains untouched until Phase 4 is fully closed.



# Phase 4 Closure - Authoritative Docker/PostgreSQL Verification

**Status: COMPLETE (2026-08-01).** Phase 4 Stages 1-4 are implemented,
integrated, and authoritatively verified. Phase 5 has not started.

## Final integration findings and fixes

- Fixed blocked-audit persistence across function-scoped pytest event
  loops. `BlockedAuditWriter` no longer obtains a globally cached engine;
  it creates its independent transaction from an `async_sessionmaker`
  bound to the caller session's active `AsyncEngine`.
- Preserved the required blocked-audit behavior: authorization failures
  remain concealed, blocked audit writes are independent of the rejected
  request transaction, and an audit-write failure never replaces the
  original authorization error.
- Updated rollback-sensitive tests to capture primitive UUID values before
  rollback expires ORM instances, eliminating invalid async lazy loads and
  `MissingGreenlet` failures.
- Updated the Phase 3 migration round-trip test so it tests revision
  `32819e0a6027` explicitly even when Phase 4's later revision is the
  repository-wide Alembic head, then restores the database to latest head.
- Applied Ruff formatting/import fixes and precise mypy annotations in the
  affected Phase 4 tests. No migration revision or dependency declaration
  was changed by these fixes.

## Authoritative verification results

- Phase 4 targeted PostgreSQL tests: **98 passed**, 0 failed.
- Final complete backend PostgreSQL suite: **311 passed**, 0 failed,
  10 dependency-deprecation warnings.
- Ruff formatting: **133 files already formatted**.
- Ruff lint: **All checks passed**.
- mypy: **Success - no issues found in 126 source files**.
- Alembic upgrade/head/current: **`e1208296dad5 (head)`**.
- Attendance/audit migration chain verified through:
  `98161483914f -> 6eeb9420bf8b -> 32819e0a6027 -> e1208296dad5`.

## Audit finding status

- AUDIT C4 is closed for attendance paths in `backend_v2`: active teacher
  assignment or admin override is enforced for write/read/stats/export
  operations, unrelated access is concealed, and blocked attempts are
  independently audited.
- The original legacy Flask implementation remains unchanged; its historical
  audit finding remains applicable until that backend is retired.

## Build and warning qualification

- A fresh `backend_v2_test` image had built successfully before runtime
  verification. A later rebuild retry failed during package resolution
  because pip could not obtain a matching `pydantic-core` distribution.
- No dependency file had changed. Final gates therefore used the previously
  successful image with the current `backend_v2` source bind-mounted at
  `/workspace`, so every final test, Ruff, mypy, and Alembic command ran
  against the actual current source tree.
- Before deployment or CI release, retry a clean image build when package
  registry/network resolution is healthy.
- The 10 pytest warnings are Starlette/httpx deprecation notices; they did
  not produce test failures and are not Phase 4 functional blockers.

## Repository safety

- No Git commit, branch, tag, stash, reset, restore, or clean operation was
  performed.
- Pre-existing legacy tracked modifications/deletions were preserved.
- Phase 4 migration `e1208296dad5` remains the current Alembic head.

## Next phase

Phase 5 is a separate phase: face enrollment and recognition workflow.
It begins only after the Phase 4 closure archive is created and verified.
ADR 0005 must be resolved before selecting or implementing the recognition
provider. Phase 4 does not include face-recognition auto-marking.


# Phase 5 Stage 1 - Provider Decision and Biometric Foundation

**Status: Stage 1 delivered this session. Stage 2 (enrollment) not started.**
Built on the verified Phase 4 closure baseline (this file's own "Phase 4
Closure" section above: 311 tests, Ruff, mypy all passing against Docker/
PostgreSQL, Alembic head `e1208296dad5`).

## What this checkpoint actually is

1. ADR 0005 (`docs/adr/0005-face-recognition-provider-pending.md`) updated
   from Proposed/Pending to **Accepted**: server-side local Python
   inference (YuNet, loaded through OpenCV's DNN/`FaceDetectorYN` API using
   `opencv-python-headless`, as the named detector, MIT-licensed) selected
   as the MVP architecture, behind the existing provider-neutral
   `detect`/`embed`/`match` boundary. `onnxruntime` is NOT required to run
   this detector and is not added in Stage 1. The paired embedding model is
   explicitly NOT locked - the commonly-paired SFace model's own license is
   unresolved: a GitHub issue on `opencv/opencv` (#21192) asking for its
   license is marked Closed (not still-open, correcting an earlier draft of
   this record) but was never answered with an explicit license statement,
   so it remains a real, tracked blocker for Stage 2/3, not glossed over.
2. `backend_v2/app/modules/face_recognition/` created from scratch:
   `domain.py` (typed value objects), `protocols.py` (`FaceDetector`/
   `FaceEmbedder`/`FaceMatcher` Protocols), `errors.py` (stable `AppError`
   subclasses), `__init__.py` (locks all five Phase 5 stages).
3. `backend_v2/app/core/config.py` extended with a `FaceRecognitionProvider`
   enum and eight new `Settings` fields (provider, model identifiers,
   detector input size, embedding dimension, match threshold/margin,
   inference device, biometric storage root, max enrollment image bytes) -
   every field fail-fast validated, every default safe/inert, one new
   cross-field rule (a non-"none" provider requires both model identifiers).
4. Two new test files / test additions:
   `backend_v2/app/tests/test_face_recognition_contracts.py` (new — value-
   object validation, Protocol conformance via deterministic fakes, and a
   structural proof that no provider contract returns an ORM model) and
   `backend_v2/app/tests/test_config.py` (extended — every new Settings
   field/validator/cross-field rule).
5. `docs/BIOMETRIC_DATA_POLICY.md` created — storage, retention, deletion,
   replacement, access, audit, API-exposure, and logging rules for future
   biometric data, explicitly scoped as application policy, not legal
   advice.
6. `docs/IMPLEMENTATION_PLAN.md` Phase 5 section replaced with the five
   locked stages (Stage 1-5, exact scope each, Stage 4 and Stage 5 kept
   distinct per instruction). `docs/ARCHITECTURE.md` §9 updated to record
   the accepted decision. `backend_v2/README.md` status line corrected
   (was stale at "Phase 4 Stage 3 in progress" despite Phase 4 being fully
   closed already) and a new Face recognition section added.
   `backend_v2/.env.example` and root `.env.example` both extended with the
   new (commented-out, safe-default) config section. `.gitignore` extended
   to cover `backend_v2`'s future biometric storage root.

## Explicitly out of scope for this checkpoint

- No detector/embedder/matcher implementation - only typed contracts and
  Protocol interfaces. No model file downloaded, vendored, or committed.
- No FastAPI router - nothing in `app.modules.face_recognition` is
  reachable over HTTP.
- No enrollment endpoint, no ORM table, no Alembic migration - Stage 1
  brief instruction 11 explicitly forbids these, and none were added.
  `app/db/models.py` and `alembic/env.py` are untouched.
- No new inference dependency (`opencv-python-headless`, `onnxruntime`,
  `numpy`, or any hosted-API SDK) added to `backend_v2/pyproject.toml`.
  Stage 1's contracts store embeddings as a plain `tuple[float, ...]` and
  images as opaque `bytes` specifically so this holds. Note `onnxruntime`
  is not needed even in Stage 3 to run the YuNet detector (OpenCV's own
  DNN module handles that internally) - it is a further-deferred decision
  for a future embedding-model adapter only, if that adapter needs it.
- No accuracy claim of any kind - ADR 0005 explicitly states real accuracy
  against this project's own classrooms is unmeasured and defers
  measurement to Stage 3/5.
- Phase 1-4 modules, migration `e1208296dad5`, and every existing API
  contract are untouched.

## Checks actually performed this session

- `python -m compileall -q app alembic scripts` (from `backend_v2/`) - see
  exact result recorded in `docs/HANDOVER_PHASE_5_STAGE_1.md`.
- Manual `py_compile` of every new/modified `.py` file individually, as
  each was written - all passed.
- Line-length scan against the configured Ruff `line-length = 100` on
  every new/modified file - 0 lines over 100 characters (four violations
  found and fixed in the new test file before this record).
- Trailing-whitespace scan on every new/modified file - 0 matches.
- Broad-exception scan (`except Exception`/bare `except:`) on the new
  module - 0 matches.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan on the new module
  and its tests - 0 matches.
- Secret/hardcoded-credential/debug-print scan on the new module - 0
  matches.
- Manual cross-check: `app/db/models.py`, `alembic/env.py`, and migration
  `e1208296dad5` are byte-for-byte unchanged from the Phase 4 closure
  baseline (no new ORM table was added, matching the Stage 1 brief).

## Checks unavailable in this sandbox

`pip install <anything>` is confirmed blocked (no network egress) and
`fastapi`/`pydantic`/`pydantic-settings`/`sqlalchemy`/`pytest`/`ruff`/`mypy`
are all confirmed not installed - consistent with every prior phase's
session in this same sandbox. As a direct consequence:

- No `pytest` collection or run of any kind (targeted or full suite).
- `ruff format --check` / `ruff check` - unavailable.
- `mypy app` - unavailable.
- `docker compose ...` - unavailable, Docker itself is not present.

No check above is claimed to have passed. Where full execution was not
possible, the closest available static verification was performed instead
(see "Checks actually performed" above) and is never conflated with the
runtime check it stands in for. The repository owner should run the full
Docker/pytest/Ruff/mypy gate before trusting this checkpoint's runtime
behavior - see `docs/HANDOVER_PHASE_5_STAGE_1.md` for the exact commands.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash was
created or performed this session. Pre-existing legacy tracked
modifications/deletions were preserved untouched.

## Next task

Phase 5 Stage 2: face enrollment and secure photo ingestion, per
`docs/IMPLEMENTATION_PLAN.md` Phase 5 Stage 2's scope and acceptance
criteria - not started in this checkpoint.


# Phase 5 Stage 2 - Biometric Enrollment and Secure Photo Ingestion

**Status: Stage 2 delivered this session. Stage 3 (detection/embedding/
matching) not started.** Built directly on the Phase 5 Stage 1 checkpoint
above (this file's own "Phase 5 Stage 1" section): Accepted ADR 0005,
provider-neutral `face_recognition` contracts, biometric configuration
foundation, `docs/BIOMETRIC_DATA_POLICY.md`. No Stage 1 decision was
reopened or changed.

## What this checkpoint actually is

1. `backend_v2/app/modules/biometric_enrollment/` created from scratch:
   `models.py` (`BiometricEnrollment`/`BiometricSample` ORM models, three
   native-enum status fields), `errors.py` (stable `AppError` subclasses),
   `storage.py` (private filesystem storage: staging/active/quarantine/
   bulk_staging zones, atomic `os.replace` promote/quarantine, opaque
   server-generated keys, path-escape/symlink guards), `image_validation.py`
   (Pillow-based decode/format/dimension/decompression-bomb/animated-image
   validation), `repository.py` (both tables), `schemas.py` (Pydantic v2,
   safe-metadata-only responses), `service.py` (create/replace/delete/
   finalize lifecycle with documented compensating cleanup), `zip_security.py`
   (pre-extraction archive + manifest validation — no `extractall()`/
   `extract()` anywhere), `bulk_service.py` (bulk ZIP orchestration, atomic
   pre-validation gate), `router.py` (thin, authorized FastAPI routes),
   `reconciliation.py` (read-only database/filesystem drift report).
2. Alembic migration `ca8e748dc8f2` (parent `e1208296dad5`, the Phase 4
   head) creates `biometric_enrollments` and `biometric_samples` plus three
   native PostgreSQL enums; clean upgrade and downgrade, downgrade leaves no
   enum type behind. `backend_v2/app/db/models.py` and
   `backend_v2/alembic/env.py` both updated to register the two new models.
3. `backend_v2/app/core/config.py` extended with seven new `Settings`
   fields (image pixel/dimension caps, bulk-ZIP byte/file/ratio/total-size
   caps, staging-timeout minutes) — every field fail-fast validated with a
   bounded range, every default conservative. `.env.example` extended with
   the matching commented-out section.
4. `backend_v2/app/api/router.py` updated to include the new
   `biometric_enrollment` router. `backend_v2/app/tests/conftest.py` updated:
   child-before-parent cleanup order extended for the two new tables, and a
   session-scoped temporary `BIOMETRIC_STORAGE_ROOT` added so storage/
   reconciliation tests never touch `var/biometric_data` in the working tree.
5. Ten new test files (`backend_v2/app/tests/`): `test_phase5_stage2_model_registration.py`,
   `test_migrations_phase5_stage2.py`, `test_phase5_stage2_storage.py`,
   `test_phase5_stage2_image_validation.py`, `test_phase5_stage2_zip_security.py`
   (includes the required `../../evil.jpg` pre-extraction rejection test),
   `test_phase5_stage2_enrollment_http.py`, `test_phase5_stage2_bulk_zip_http.py`,
   `test_phase5_stage2_failure_injection.py`, `test_phase5_stage2_reconciliation.py`,
   plus a shared `phase5_stage2_http_helpers.py` fixture module (reuses
   `phase3_http_helpers.py`'s `seed_user`/`auth_headers`/`create_resource`
   as-is).
6. `docs/ARCHITECTURE.md` §9 extended with the Stage 2 design summary.
   `docs/IMPLEMENTATION_PLAN.md`'s Phase 5 Stage 2 entry marked COMPLETE
   with acceptance criteria individually confirmed met.
   `docs/BIOMETRIC_DATA_POLICY.md` extended with the Stage 2 implementation
   notes (storage layout, lifecycle states, manifest format) below its
   Stage 1 policy text (the Stage 1 policy itself is unchanged).
   `backend_v2/README.md` status line updated; a "Biometric enrollment"
   section added alongside the existing "Face recognition" one.
   `docs/HANDOVER_PHASE_5_STAGE_2.md` created (full design, exact file
   list, exact check results, known risks, Stage 3 starting point).

## Design decisions made this session (none contradict Stage 1)

- **Enrollment/replace/delete/bulk-create are admin-only**, with no
  object-level ownership-check dependency (unlike attendance's teacher-
  classroom scope check) — because `docs/BIOMETRIC_DATA_POLICY.md`'s
  Stage 1, Accepted policy already settles this: there is no teacher role
  in the enrollment picture at all, so there is no "right role, wrong
  scope" case to guard against the way there is for a teacher and a
  classroom. The one object-level check in this module is the self-
  service *read* path (a student may read only their own enrollment),
  which reuses the same concealed-404 + `BlockedAuditWriter` pattern as
  `app.modules.profiles.student_router`/`app.modules.attendance.service`.
- **`storage_key` is a separate, server-generated value from the row's own
  `id`** (both are UUID-shaped today, deliberately decoupled) — defense in
  depth so a database-identity value is never also a filesystem-locator
  value, and so a future storage-layout change never requires renumbering
  primary keys.
- **A partial unique index enforces "at most one ACTIVE sample per
  enrollment" at the database layer**, not just in service code — matching
  this codebase's existing preference (attendance's composite unique
  constraint) for database-enforced invariants over application-only
  assumptions.
- **Bulk ZIP enrollment's atomicity is achieved by never starting a write
  until every row is already known-good** (a two-phase validate-then-
  execute design), not by attempting all writes and rolling back a partial
  failure — documented as the one honest way to give a strong atomicity
  guarantee given that a SQL transaction cannot roll back a filesystem
  rename. The one exception (a genuine infrastructure failure partway
  through the execution phase, after every row already passed validation)
  is explicitly named as a known risk, not hidden.
- **`except Exception` is used in six places** across `service.py`/
  `bulk_service.py`, each with an inline comment explaining why a broad
  catch is necessary there specifically (a compensating-cleanup step that
  must run regardless of the failure's exact type, or a best-effort
  secondary operation that must never mask the primary result/error) —
  Ruff's configured rule set (`E, F, I, UP, B, C4, SIM, RUF`) does not
  include `BLE001` (flake8-blind-except), so no `# noqa: BLE001` comment is
  added anywhere (that would be decorative, not a real lint suppression);
  this matches `app.modules.attendance.service`'s own existing, un-
  annotated `except Exception` convention. Two sites that could be
  narrowed safely (catching only `AppError`, per `validate_image_file`'s
  own documented contract of never raising anything else) were narrowed.

## Explicitly out of scope for this checkpoint

- No face detection, alignment, embedding, or matching code anywhere —
  `RecognitionProcessingState` exists as a column precisely so no Stage 2
  code path can claim a sample is recognition-ready; every Stage 2 write
  to that column is `pending_processing`, never `processed`.
- No new inference dependency. The only dependency Stage 2 adds is
  Pillow (`pillow`, already a transitive dependency of nothing else in
  this project, added explicitly to `pyproject.toml`) — no
  `opencv-python-headless`, `onnxruntime`, `numpy`-for-inference,
  TensorFlow, PyTorch, MTCNN, InsightFace, DeepFace, or hosted face-API
  SDK anywhere.
- No camera/frontend work of any kind.
- No modification to Phase 1-4 migrations, Phase 4 attendance API
  contracts, or any legacy Flask/React code.
- No Git operation of any kind (no commit, branch, tag, reset, restore,
  checkout, clean, or stash).

## Checks actually performed this session

- `python -m compileall -q app alembic` (from `backend_v2/`) — passed, 0
  errors, across every new/modified file.
- A custom AST-based unused-import scan across every new/modified file —
  0 findings after two intentionally-unused imports (caught by the scan
  itself) were removed during the session.
- A CRLF-safe line-length scan against the configured Ruff
  `line-length = 100` across every new/modified file — 0 lines over 100
  characters (all violations found during the session were fixed before
  this record; the scan strips a trailing `\r` before measuring, so it is
  accurate against this repository's pre-existing mixed line endings).
- Trailing-whitespace scan across every new/modified file — 0 matches.
- Broad-exception scan (`except Exception`/bare `except:`) across the new
  module — 6 matches, each reviewed individually this session (see
  "Design decisions" above); every one either re-raises unchanged after a
  compensating action, or is an explicitly-documented best-effort
  secondary operation that must not mask the primary result.
- TODO/FIXME/`NotImplementedError`/fake-assertion scan across the new
  module and its tests — 0 matches (two `NotImplementedError`-adjacent
  strings appear only inside docstrings describing what Stage 3 will
  implement, not as executable placeholder code).
- Secret/hardcoded-credential/debug-print scan across the new module —
  0 matches.
- Cache/`__pycache__`/`.pyc`/real-`.env`/model-file scan across the
  session's changes — 0 matches (no binary or cache artifact was ever
  written under version-controlled paths; the deliverable ZIP explicitly
  excludes `__pycache__`/`.pyc`/`.venv`/`node_modules`/any real `.env`).
- Manual, file-by-file scope scan confirming no Stage 3-5 functionality
  (detection/embedding/matching/recognition-attendance) exists anywhere
  in the new module, and that `app/modules/face_recognition/` is
  byte-for-byte unchanged from the Phase 5 Stage 1 checkpoint.
- Two standalone, real-source verification runs (not mere static review):
  `zip_security.py`'s actual production functions were executed
  (dependency-injected against lightweight stand-ins for
  `app.core.config.Settings`/the two `AppError` subclasses it imports,
  since neither `pydantic` nor `fastapi` is installed in this sandbox)
  against real ZIP archives built with `zipfile`, including the required
  `../../evil.jpg` regression, a symlink entry, an encrypted entry (binary-
  patched into the archive's local/central-directory flag bits, since
  `zipfile.ZipFile.writestr` does not preserve a manually-set
  `ZipInfo.flag_bits`), duplicate/missing/invalid manifest rows, and
  suspicious-compression-ratio content — every scenario behaved exactly as
  the corresponding pytest test expects. `storage.py`'s actual production
  functions were executed the same way, confirming the staging/active/
  quarantine lifecycle, byte-cap enforcement and cleanup, and the internal
  path-escape invariant.

## Checks unavailable in this sandbox — same historical limitation

`pip install <anything>` is confirmed blocked (no network egress) and
`fastapi`/`pydantic`/`pydantic-settings`/`sqlalchemy`/`pytest`/`ruff`/`mypy`
are all confirmed not installed — consistent with every prior phase's
session in this same sandbox, including Phase 5 Stage 1's checkpoint
above. Only `Pillow` (needed for image validation, and already present in
this sandbox) could be exercised directly. As a direct consequence:

- No `pytest` collection or run of any kind (targeted or full suite) — all
  ten new test files are written and `py_compile`-clean but have never
  been executed by a test runner.
- `ruff format --check` / `ruff check` — unavailable; the CRLF-safe
  line-length scan and the AST-based import scan above are the closest
  static substitutes actually run, and are not conflated with a real Ruff
  pass.
- `mypy app` — unavailable.
- `alembic upgrade head` / `alembic downgrade` — unavailable (no reachable
  PostgreSQL instance). The migration file was reviewed line-by-line
  against the Phase 4 migration's exact structure/style instead, and the
  round-trip test (`test_migrations_phase5_stage2.py`) is written to
  self-skip cleanly (not fail) if no database is reachable, matching
  `test_migrations_phase4.py`'s own established pattern.
- `docker compose ...` — unavailable, Docker itself is not present.

No check above is claimed to have passed where it was not actually run.
Where full execution was not possible, the closest available static or
standalone-source verification was performed instead (see "Checks
actually performed" above) and is never presented as equivalent to the
runtime check it stands in for. The repository owner should run the full
Docker/pytest/Ruff/mypy gate — starting with `alembic upgrade head` to
confirm the migration applies cleanly against a real PostgreSQL instance —
before trusting this checkpoint's runtime behavior.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash was
created or performed this session. Pre-existing legacy tracked
modifications/deletions were preserved untouched.

## Correction-patch session — Phase 5 Stage 2 v2

**Status: a dedicated correction patch, working from the delivered
`ShikshaSathi-phase-5-stage-2.zip` as the sole authoritative baseline (no
re-inspection of already-correct code, no Stage 3 work). Fixed eight
confirmed defects found by review; produced
`ShikshaSathi-phase-5-stage-2-v2.zip`. See
`docs/HANDOVER_PHASE_5_STAGE_2.md`'s "Correction patch applied after
initial delivery" section for the full per-item rationale — this entry
is the session log, not a duplicate of that explanation.**

### The eight corrections (summary — see handover doc for full detail)

1. `models.py` — `CheckConstraint` names were double-prefixed by the
   shared naming convention (`name=` was already-prefixed, but a
   `CheckConstraint`'s `name=` *is* the `%(constraint_name)s` token
   source). Fixed to bare names (`width_px_positive`, etc.).
2. `test_phase5_stage2_image_validation.py` — the pixel-cap test
   configured `MAX_ENROLLMENT_IMAGE_PIXELS=100_000`, below `Settings`'s
   own field-validator minimum of `1_000_000`, so the test would fail at
   `Settings` construction before reaching the code under test. Fixed to
   `1_000_000` with a `1100x1000` fixture image.
3. `service.py` / `repository.py` — enrollment deletion drained only a
   single sample and then unconditionally marked the enrollment
   `DELETED`, permanently orphaning a stalled `REPLACEMENT_PENDING`
   sample's row and file if a prior replace's best-effort retirement had
   failed. Fixed via a new `list_live_for_enrollment` repository method
   and a rewritten `_advance_deletion`/`_advance_sample_deletion` that
   drains every live sample (PENDING/ACTIVE/REPLACEMENT_PENDING/
   DELETION_PENDING/QUARANTINED) and re-checks for drift instead of
   returning early solely because `enrollment.status` already reads
   DELETED.
4. `zip_security.py` — bulk-manifest duplicate-student detection compared
   raw manifest text, not the parsed `uuid.UUID` value, so
   differently-cased/braced spellings of the same student's ID evaded
   detection. Fixed to dedupe on `str(uuid.UUID(...))`.
5. `bulk_service.py` — an oversized bulk ZIP raised the single-image
   `EnrollmentImageTooLargeError` instead of the archive-level
   `BulkEnrollmentZipTooLargeError`. Fixed.
6. `service.py` / `bulk_service.py` — no compensation existed for a DB/
   audit-write failure occurring strictly *after* `promote()` had already
   (irreversibly) moved a file into `active/`, in `create_sample`,
   `replace_sample`, and bulk row execution — leaving an orphaned active
   file with no matching row. Fixed with a new
   `_compensate_promoted_file_after_activation_failure` helper (re-reads
   the sample fresh from the database rather than trusting a possibly
   stale in-memory object after rollback; quarantines and purges the
   orphaned file; removes the now-meaningless row; never re-raises its
   own failure) wrapped around the final activate/audit transaction in
   all three call sites. Also added a staged-file discard to
   `_execute_rows`'s per-row exception handler so every row that fails
   during bulk execution, for any reason, has its staged file cleaned up.
7. `bulk_service.py` — an archive-level rejection (malformed ZIP, path
   traversal, missing manifest — anything `validate_archive` itself
   raises, before any row is ever reached) wrote no audit record at all,
   unlike a row-level rejection. Fixed to write the same `BLOCKED`
   bulk-attempt audit (aggregate counts only) before re-raising the
   original error unchanged.
8. `test_migrations_phase5_stage2.py` — the round-trip test assumed
   `"head" == ca8e748dc8f2`, which breaks the moment Stage 3 adds a
   migration. Fixed to upgrade to the true latest head first, move
   explicitly to `ca8e748dc8f2` for every Stage-2 assertion, downgrade to
   the Phase 4 head `e1208296dad5`, re-upgrade specifically to
   `ca8e748dc8f2` (not `"head"`), and restore the true latest head in a
   `finally` block regardless of outcome.

### Exact files modified this session

```
backend_v2/app/modules/biometric_enrollment/models.py
backend_v2/app/modules/biometric_enrollment/service.py
backend_v2/app/modules/biometric_enrollment/repository.py
backend_v2/app/modules/biometric_enrollment/bulk_service.py
backend_v2/app/modules/biometric_enrollment/zip_security.py

backend_v2/app/tests/test_phase5_stage2_image_validation.py
backend_v2/app/tests/test_phase5_stage2_failure_injection.py
backend_v2/app/tests/test_phase5_stage2_bulk_zip_http.py
backend_v2/app/tests/test_phase5_stage2_zip_security.py
backend_v2/app/tests/test_migrations_phase5_stage2.py

docs/HANDOVER_PHASE_5_STAGE_2.md
docs/PROGRESS.md
```

No other file was touched. In particular: no migration file, no router,
no Pydantic schema, no `app/modules/face_recognition/` file, and no
legacy `backend/`/`frontend/` file.

### Exact tests added this session

- `test_phase5_stage2_zip_security.py`:
  `test_duplicate_student_row_different_uuid_representation_is_rejected`
- `test_phase5_stage2_bulk_zip_http.py`:
  `test_bulk_oversized_zip_returns_413_with_correct_error_code`,
  `test_bulk_archive_level_rejection_writes_blocked_audit`
- `test_phase5_stage2_failure_injection.py`:
  `test_finalize_deletion_drains_stalled_replacement_artifact_too`,
  `test_create_sample_activation_failure_after_promote_leaves_no_falsely_active_sample`,
  `test_create_sample_activation_failure_allows_retry_after_fix`,
  `test_replace_sample_activation_failure_preserves_old_active_sample`,
  `test_bulk_activation_failure_after_promote_compensates_and_reports_row_failed`,
  `test_bulk_execution_failure_discards_staged_file_for_every_failed_row`
- `test_migrations_phase5_stage2.py`: no new test function — the single
  existing `test_phase5_stage2_migration_round_trip` was rewritten in
  place per item 8 above (an earlier in-session edit accidentally left
  the old function body duplicated as dead code after the new one; this
  was caught by a `view` immediately after the edit and removed before
  any check was run — noted here for an honest, complete record of the
  session, not because it survived into any delivered file).

### Checks actually performed this session

- `python3 -m compileall -q app alembic` (from `backend_v2/`) — 0 errors,
  across the entire tree (not only the modified files).
- A symtable-based free-variable ("could this raise `NameError`") scan
  across every file modified this session — 0 genuine findings. The scan
  flagged six closures as "possible issues"
  (`app/modules/biometric_enrollment/zip_security.py`'s two pre-existing,
  untouched closures at lines 199-207/394/424, and four legitimate
  closures inside this session's own new test helpers/monkeypatch
  wrappers in `test_phase5_stage2_failure_injection.py` and
  `test_phase5_stage2_bulk_zip_http.py`) — all six are ordinary Python
  closures over an *enclosing function's* locals, which this
  module-scope-only scan cannot see past; each was checked by hand and
  confirmed correct.
- CRLF-safe line-length scan (configured Ruff `line-length = 100`) across
  every file modified this session — 0 lines over 100 characters.
- Trailing-whitespace and hard-tab scan across every file modified this
  session — 0 matches.
- Bare `except:` scan across every file modified this session — 0
  matches. `except Exception`/`except Exception as exc` sites introduced
  this session (four in `service.py`, four in `bulk_service.py`) were
  each reviewed individually: every one either re-raises the original
  error unchanged after a best-effort compensating action, or is the
  compensating action itself (which must never let its own failure mask
  the original error) — each carries a plain prose comment explaining
  this at its call site, matching the module's existing convention.
- TODO/FIXME/XXX scan across every file modified this session — 0
  matches.
- Hardcoded-secret/credential pattern scan across every file modified
  this session — 0 genuine matches (`_VALID_SECRET = "a" * 40"` in two
  test files' pre-existing fixture setup is a synthetic placeholder, not
  a real credential — flagged only by the pattern's own breadth, not a
  real finding, and not something this session introduced).
- Duplicate function/class-definition scan (by exact qualified name)
  across every file modified this session — 0 duplicates, including a
  targeted re-check of `test_migrations_phase5_stage2.py` after the
  dead-code duplication mentioned above was caught and removed.
- Manual scope re-scan confirming no Stage 3-5 functionality
  (detection/embedding/matching/recognition-attendance/OpenCV/ONNX/model
  file) exists anywhere in this session's changes, and that
  `app/modules/face_recognition/` remains byte-for-byte unchanged.
- Cache/`__pycache__`/`.pyc`/real-`.env` scan across the working tree
  before packaging — any interpreter-generated cache directories were
  removed before the delivery ZIP was built (see "Packaging" below).

### Checks unavailable in this sandbox — same historical limitation

`pip install <anything>` is confirmed blocked (no network egress) and
`fastapi`/`pydantic`/`pydantic-settings`/`sqlalchemy`/`pytest`/`ruff`/
`mypy` are all confirmed not installed — consistent with every prior
session in this sandbox, including the original Phase 5 Stage 2 delivery
above. As a direct consequence:

- No `pytest` collection or run of any kind. All five newly-added test
  functions (plus the two rewritten tests) are `py_compile`-clean and
  were checked by hand against the exact production code paths they
  exercise, but have never been executed by a real test runner.
- `ruff format --check` / `ruff check` — unavailable; the CRLF-safe
  line-length scan and the symtable-based free-variable scan above are
  the closest static substitutes actually run, and are not conflated
  with a real Ruff pass.
- `mypy app` — unavailable.
- `alembic upgrade head` / `alembic downgrade` — unavailable (no
  reachable PostgreSQL instance). The rewritten
  `test_migrations_phase5_stage2.py` was re-read end-to-end after the
  duplication fix to confirm it is syntactically a single, correctly
  structured function with one `try`/`finally`, and its
  `command.upgrade`/`command.downgrade` call sequence was checked by hand
  against `PHASE5_STAGE2_HEAD_REVISION` (`ca8e748dc8f2`) and
  `PHASE4_HEAD_REVISION` (`e1208296dad5`) — but it has not actually been
  run against a database this session, same as the original delivery.
- `docker compose ...` — unavailable, Docker itself is not present.

No check above is claimed to have passed where it was not actually run.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash was
created or performed this session. Pre-existing legacy tracked
modifications/deletions were preserved untouched.

## Correction-patch session — Phase 5 Stage 2 v3

**Status: a second, single-item, test-only correction patch, working
from the delivered `ShikshaSathi-phase-5-stage-2-v2.zip` as the sole
authoritative baseline. Fixed one confirmed defect in the v2 patch's own
item 8 fix; produced `ShikshaSathi-phase-5-stage-2-v3.zip`. See
`docs/HANDOVER_PHASE_5_STAGE_2.md`'s "Second correction patch (v3) —
migration test upgrade/downgrade fix" section for the full rationale —
this entry is the session log, not a duplicate of that explanation.**

### The one correction

`test_migrations_phase5_stage2.py` — the v2 patch's item 8 fix moved
from true latest head to this stage's own revision
(`PHASE5_STAGE2_HEAD_REVISION`) via `command.upgrade(cfg,
PHASE5_STAGE2_HEAD_REVISION)`. That is only a valid move while
`ca8e748dc8f2` is still the true head; once Stage 3 adds a migration on
top of it, `ca8e748dc8f2` becomes an ancestor of true head, so the same
move must be a `command.downgrade`. Fixed by changing that one call from
`command.upgrade` to `command.downgrade`. The later re-upgrade to
`PHASE5_STAGE2_HEAD_REVISION` (after the explicit downgrade to the Phase
4 head, `e1208296dad5`) was already correct and left unchanged. The
function's docstring was tightened to describe the first move as
head-relative rather than unconditionally "up."

### Exact files modified this session

```
backend_v2/app/tests/test_migrations_phase5_stage2.py

docs/HANDOVER_PHASE_5_STAGE_2.md
docs/PROGRESS.md
```

No file outside this list was touched. No application code, migration
file, model, router, schema file, or unrelated test was touched.

### Checks actually performed this session

- `python3 -m compileall -q app` (from `backend_v2/`) — **passed**, 0
  errors.
- Full re-read of `test_migrations_phase5_stage2.py` end-to-end,
  confirming: the change is exactly the one intended line; the later
  `command.upgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)` re-upgrade call was
  correctly left unchanged; the single `try`/`finally` structure and the
  `finally` block's own `command.upgrade(cfg, "head")` are both
  unchanged.
- Duplicate-definition and CRLF-safe line-length scans re-run against the
  one changed file — 0 duplicates, 0 lines over 100 characters.
- Scope re-scan: confirmed no file other than the one test file and the
  two documentation files above was touched; Stage 3 was not started;
  `app/modules/face_recognition/` was never opened this session.

### Checks unavailable in this sandbox — same historical limitation

`pytest`/`alembic`/`sqlalchemy`/`asyncpg` remain not installed and no
PostgreSQL instance is reachable, identical to both prior sessions.

- No `pytest` collection or run. The fix was verified by re-reading the
  function, not by executing it.
- `alembic upgrade head` / `downgrade` — unavailable; the corrected
  `command.downgrade(cfg, PHASE5_STAGE2_HEAD_REVISION)` call was checked
  against the same revision constants already used and verified-by-hand
  in the v2 correction, but not run against a database this session.

No check above is claimed to have passed where it was not actually run.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash was
created or performed this session. Pre-existing legacy tracked
modifications/deletions were preserved untouched.

## Session: Phase 5 Stage 3 — detection, embedding, and matching pipeline

**Status: COMPLETE this session.** Full detail:
`docs/HANDOVER_PHASE_5_STAGE_3.md`,
`docs/adr/0011-phase5-stage3-embedding-model-and-matching.md`.
Summary only, here — do not duplicate the full handover's content.

### What was built

Real YuNet (OpenCV `cv2.FaceDetectorYN`) detection, a standalone
landmark-driven alignment stage, real embedding via dlib's
`dlib_face_recognition_resnet_model_v1` (128-D, L2-normalized), a
candidate-scoped cosine-similarity matcher with best-sample-per-student
aggregation, a new `biometric_embeddings` table (migration
`d22bce264ecd`, parent `ca8e748dc8f2` — Stage 2's own migration file
was not touched), the enrollment-sample processing lifecycle
(`PENDING_PROCESSING` → `PROCESSED`/`PROCESSING_FAILED`, safe retry,
bounded batch), safe provider-health reporting, a synthetic-data-only
FAR/FRR evaluation harness, and five admin-only API endpoints. No
recognition-attendance endpoint, no `AttendanceService` call, no
`AttendanceRecord` write — confirmed both statically and by a dynamic
zero-row-count test.

### Embedding model decision

`dlib_face_recognition_resnet_model_v1`, selected over InsightFace/
ArcFace's `buffalo_l` family (rejected — explicit non-commercial-
research-only license) and SFace (still blocked, unchanged from ADR
0005). The dlib *library*'s license (Boost Software License 1.0) and
the model *weight file*'s license (public domain, per the model
author's own repeated statements — not a bundled machine-readable
license file) are kept explicitly distinct throughout ADR 0011 and the
Stage 3 handover, including an honest note on the strength of that
evidence and on the separate, unresolved question of the model's
upstream training-data provenance. No model weight was downloaded,
vendored, or committed anywhere in this checkpoint.

### Threshold

`FACE_MATCH_THRESHOLD` changed from Stage 1's placeholder `0.90` to
`0.82` — a **provisional structural default**, mathematically derived
from dlib's own published Euclidean-distance guidance
(`cosine = 1 - (0.6^2 / 2) = 0.82`), explicitly **not** a value
calibrated against this project's own classroom data. Real calibration
remains pending — stated as such everywhere this value is documented.

### A genuine defect found and fixed during this session's own review

The Stage 3 brief refined `FaceMatcher.match`'s signature from Stage
1's `match(embedding)` to `match(embedding, candidates)` (an additive
refinement of a contract Stage 1 left open, not a rewrite of
implemented behavior — no Stage 1/2 matcher implementation existed to
break). The one Stage 1 test file exercising this protocol
(`test_face_recognition_contracts.py`) still used the old one-argument
signature in its own fake matcher and every call site — a real,
caught-and-fixed staleness bug, not a crash (Python does not enforce
`Protocol` method signatures at runtime, only method presence), but a
genuine correctness/documentation defect that a proper
implementation-vs-tests review this session found and corrected in
place — minimal surface, no protocol redesign.

A second genuine bug was found by a purpose-built undefined-name
scanner (distinct from, and a necessary complement to, an unused-
import scanner): `test_phase5_stage3_api_http.py` referenced a helper,
`patch_providers`, without importing it — would have raised
`NameError` at test-collection time. Fixed. The scanner was then run
across the whole `backend_v2/app` tree; its one other finding (`ItemT`
in a pre-existing, non-Stage-3 file using PEP 695 generic-class syntax)
was confirmed a scanner false positive, not a real bug, and left
untouched as out of Stage 3 scope.

### Exact files created/modified this session

See `docs/HANDOVER_PHASE_5_STAGE_3.md`'s "Exact files created" /
"Exact files modified" sections for the complete, exact list — not
duplicated here to avoid the two documents drifting out of sync.

### Checks actually performed this session

- `python3 -m compileall -q app alembic scripts` (from `backend_v2/`)
  — **passed**, 0 errors.
- Full-tree `ast.parse` over every `.py` file under `backend_v2/` —
  **passed**, 0 syntax errors.
- Custom AST-based unused-import scan (Stage 3 files, then whole tree)
  — found and fixed one unused import.
- Custom AST-based undefined-name scan (Stage 3 files, then whole
  tree) — found and fixed one real bug (see above); one confirmed
  false positive in pre-existing, non-Stage-3 code, left untouched.
- Duplicate top-level-definition scan, bare-`except:`/TODO/FIXME scan,
  line-length (100-char) scan — all run against every Stage 3 file;
  line-length violations found and fixed (11 in implementation files,
  7+ in test files); everything else passed clean.
- Secret/credential, absolute-path-leak, `.git`/real-`.env`/cache/pyc/
  venv/node_modules, and biometric-image/exported-embedding/model-
  weight scans over the final packaged tree before zipping — see the
  Stage 3 handover and this session's final report for exact results.
- Standalone numeric verification (using this sandbox's real,
  installed `numpy`/`opencv-python-headless`) of the alignment
  transform's degenerate-case handling, the cosine/Euclidean identity
  behind the 0.82 threshold, and every hand-picked similarity value
  asserted in the matcher/evaluation test files — confirms these
  values against the real algorithm, not just an assumption. Caught
  and fixed one bug this way before it ever reached a test file: an
  early embedding-vector test generator used modular arithmetic that
  silently aliased different seeds to identical vectors.

### Checks unavailable in this sandbox — same historical limitation

`fastapi`/`pydantic`/`sqlalchemy`/`pytest`/`alembic`/`dlib`/
`structlog`/`asyncpg`/`httpx`/`argon2-cffi`/`ruff`/`mypy` remain not
installed, and there is no network egress (confirmed via a dry-run
`pip install`), identical in kind to every prior Phase 5 session. This
sandbox does have `numpy`/`opencv-python-headless`/`Pillow` installed,
which is new relative to earlier sessions and is what made the
standalone numeric verification above possible — but the application
itself still cannot be imported.

- No `pytest` collection or run (targeted or full suite).
- No `ruff format --check` / `ruff check` / `mypy` run.
- No `alembic upgrade`/`downgrade` run against a real PostgreSQL
  database — the Stage 3 migration round-trip test
  (`test_migrations_phase5_stage3.py`) is written, reviewed, and
  self-skips cleanly when no database is reachable, but has not been
  proven to pass by actually running it.
- No real-model smoke test — no `.onnx`/`.dat` file exists in this
  sandbox, and none was downloaded.

No check above is claimed to have passed where it was not actually
run.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash
was created or performed this session.

## Correction-patch session — Phase 5 Stage 3 v2

**Status: one targeted correction patch fixing five independently-
confirmed Stage 3 findings, working from the delivered
`ShikshaSathi-phase-5-stage-3.zip` as the sole authoritative baseline.
Produced `ShikshaSathi-phase-5-stage-3-v2.zip`. See
`docs/HANDOVER_PHASE_5_STAGE_3.md`'s "Stage 3 v2 correction patch"
section for the full rationale — this entry is the session log, not a
duplicate of that explanation.**

**This session had, for the first time, real network egress and a real
local PostgreSQL 16 instance — every check below was actually run, not
statically reasoned about.**

### The five corrections

1. **Config test regression** — `test_config.py`'s stale success test
   (only supplied model identifiers, not the also-required model
   paths) fixed and renamed; four missing rejection tests added.
   `Settings` validator itself unchanged/not weakened.
2. **Process-vs-retry state contract** — `process_sample` previously
   let a `PROCESSING_FAILED` sample fall through as if it were fresh;
   fixed to an explicit `ACTIVE + PENDING_PROCESSING`-only allow-list.
   One new regression test proves the full fail → rejected →
   `retry_sample` → succeeds cycle, passing against real PostgreSQL.
3. **Event-loop offload + provider serialization** — sample processing
   and match-probe's detect→align→embed work now runs via
   `asyncio.to_thread`; `/health` offloads provider-readiness loading
   too. Cached `YuNetFaceDetector`/`DlibResnetFaceEmbedder` instances
   now carry a per-instance `threading.RLock` (not a global lock)
   serializing lazy loading and inference; `provider_factory.py` also
   gained a narrow cache-populate lock. Provider Protocols remain
   synchronous, unchanged. 6 new tests.
4. **Match-probe audit** — `MatchingService.match_probe` now requires
   `actor`/`request_id` and writes exactly one audit row per call
   (`SUCCESS` with candidate count/match status/matched student ID;
   `BLOCKED` with a reason code for an empty candidate scope) via the
   existing `AuditLogRepository`/`service_transaction` pattern. Never
   audits an embedding, image bytes, a path, or a raw exception. 5 new
   tests.
5. **Match-probe image safety** — the probe upload's only protection
   was an 8 MiB byte cap; brought up to Stage 2's full decoded-content
   protection class (decompression-bomb guard, pixel/dimension caps,
   JPEG/PNG/WEBP allowlist, animated-image rejection) by refactoring
   Stage 2's `image_validation.py` to share its actual check logic via
   a new, error-taxonomy-neutral private core — Stage 2's own public
   behavior is unchanged (all 13 pre-existing Stage 2 tests still pass
   unmodified). New `match_probe_validation.py` + `MatchProbeImage*`
   error family (not reusing Stage 2's `Enrollment*` error names). 13
   new tests.

### Known, out-of-scope discovery: Stage 2 `MissingGreenlet` defect

Real PostgreSQL access surfaced a **pre-existing Stage 2 defect** —
`biometric_enrollment/service.py::create_sample` raises
`MissingGreenlet` serializing its response after commit — never seen
before because no prior session had a real database. Deliberately
**not fixed** here (out of this Stage 3-only patch's scope). Every
existing Stage 2/Stage 3 test that seeds via the real HTTP upload path
(`upload_sample`) fails against a real database because of it — this
is exactly Category B below. New helper
`app.tests.phase5_stage3_helpers.seed_active_sample_direct` seeds an
`ACTIVE` sample via direct ORM/repository calls (same primitives Stage
2's service uses, minus its buggy serialization step) so every new/
modified test in this patch is independent of the blocker. No Stage 3
assertion was weakened or skipped to work around it.

### Exact files modified/added this session

```
backend_v2/app/core/config.py                                         (unchanged — validator confirmed correct, not touched)
backend_v2/app/modules/face_recognition/processing_service.py
backend_v2/app/modules/face_recognition/matching_service.py
backend_v2/app/modules/face_recognition/router.py
backend_v2/app/modules/face_recognition/errors.py
backend_v2/app/modules/face_recognition/match_probe_validation.py     (new)
backend_v2/app/modules/face_recognition/provider_factory.py
backend_v2/app/modules/face_recognition/providers/yunet_detector.py
backend_v2/app/modules/face_recognition/providers/dlib_embedder.py
backend_v2/app/modules/biometric_enrollment/image_validation.py

backend_v2/app/tests/test_config.py
backend_v2/app/tests/test_phase5_stage3_processing_service.py
backend_v2/app/tests/test_phase5_stage3_matching_service.py
backend_v2/app/tests/phase5_stage3_helpers.py
backend_v2/app/tests/test_phase5_stage3_offload_and_locking.py        (new)
backend_v2/app/tests/test_phase5_stage3_match_probe_audit.py          (new)
backend_v2/app/tests/test_phase5_stage3_match_probe_image_validation.py (new)

docs/HANDOVER_PHASE_5_STAGE_3.md
docs/PROGRESS.md
```

No Stage 1/2 migration touched. No Stage 2 application code touched.
No legacy Flask/React file touched. No real `.env` touched. No model
weight packaged. Stage 4 not started.

### Checks actually performed this session (real, not static)

- `python -m compileall -q app alembic scripts` — **passed**, 0 errors.
- Real local PostgreSQL 16 (`apt`-installed): `alembic upgrade head`
  from empty — **passed** through every migration; `alembic current`
  confirms `d22bce264ecd (head)`, parent `ca8e748dc8f2`.
- `test_migrations_phase5_stage3.py` (the Stage 3 round-trip test) —
  **passed** (1 passed) against the real database.
- `test_phase5_stage2_image_validation.py` — **13 passed**, unchanged.
- Targeted Stage 3 correction tests (all 5 findings) — **all passing**
  against real PostgreSQL where DB-backed.
- Full suite, real PostgreSQL: **652 collected, 606 passed, 46
  failed.**
  - **Category A (this patch's own regressions): 0.**
  - **Category B (confirmed pre-existing Stage 2 `MissingGreenlet`
    fallout): 45.**
  - **Category C (unrelated, pre-existing): 1** —
    `test_migrations_phase4.py::test_phase4_stage1_migration_round_trip`,
    which fails on any complete migration-to-head run once later
    migrations exist, independent of this patch.
- `ruff format --check` (full tree) — 17 files need reformatting, all
  confirmed pre-existing/untouched by this patch; the 5 touched files
  that needed it were formatted.
- `ruff check` (full tree) — 23 findings remain; only 5 are in files
  this patch touched, and all 5 are on lines this patch did not
  change — none introduced by this patch, none fixed (historical
  debt, out of scope).
- `mypy app` (full tree) — 162 errors in 17 files; 6 of those files
  were touched/created by this patch (69 of the 162 errors), every
  one the same pre-existing, codebase-wide test-authoring pattern
  (`no-untyped-def`, duck-typed fakes vs. concrete parameter types)
  already present in the other 11 untouched flagged files —
  confirmed no genuine new typing defect in any file this patch
  changed; nothing fixed (historical debt, out of scope).
- Static secret/path/cache/model-weight/image/embedding/archive scan
  over the working tree — clean; only expected generated caches found
  (removed before packaging); no real secret, no sandbox-path leak.
- Real-model smoke test — **NOT RUN**: no `.onnx`/`.dat` model file
  exists in this sandbox and none was downloaded/built, per the
  explicit "no model weights" constraint every session has honored.
  `dlib` itself was not built from source either (impractical in this
  single-core sandbox with no persistent background process across
  tool calls) — not needed, since the whole suite fakes `dlib` via
  `sys.modules` injection.

No check above is claimed to have passed where it was not actually
run.

## Correction-patch session — Phase 5 Stage 3 v3

**Status: one tiny, targeted patch fixing two independently-confirmed
issues in the v2 correction patch, working from the v2 ZIP (verified
by SHA-256) as the sole baseline. Produced
`ShikshaSathi-phase-5-stage-3-v3.zip`. See
`docs/HANDOVER_PHASE_5_STAGE_3.md`'s "Stage 3 v3 correction patch"
section for full detail; this is the session log.**

### The two fixes

1. **Pillow global-state concurrency race** —
   `_validate_decoded_bytes` mutated process-global
   `Image.MAX_IMAGE_PIXELS` with no synchronization; once match-probe
   validation started running via `asyncio.to_thread` (v2), concurrent
   requests could interleave the mutate/restore pair — independently
   reproduced (Pillow's real default 89478485 got stuck at a smaller
   configured value, 30000000). Fixed with a cheap header-only
   pre-check (rejects an oversized declared size before any expensive
   decode, touching no global state) plus a new `threading.Lock`
   (`_max_image_pixels_lock`) serializing the remaining full-decode
   critical section that does still touch the global. Decompression-
   bomb/max-pixel/max-dimension protection unchanged in effect. New
   concurrency regression test (60 concurrent calls, 5 distinct
   configured caps, tiny 50x50 fixture) passes 5/5; confirmed it
   catches the regression when the lock is temporarily removed (2/5
   failures, matching real thread-race timing variance).
2. **HTTP empty-scope BLOCKED audit bypass** — `router.match_probe`
   had its own separate empty-scope check that ran *before*
   `MatchingService` was even constructed, so the v2-added `BLOCKED`
   audit was dead code for every real HTTP request. Fixed by
   extracting `MatchingService.ensure_candidate_scope(...)` and having
   the router call it first (before any file I/O), with `match_probe`
   itself also calling it as a no-duplicate-audit defensive first
   step. Framework-level request-parsing rejections (before the
   endpoint body runs at all) remain unaudited by design — documented,
   not worked around. Three new regression tests, including the actual
   HTTP-shaped repro (empty scope + a fake upload file that raises if
   `read()` is ever called) — all pass against real PostgreSQL.

### Checks run this session (scoped)

- Stage 2 image-validation: **13 passed**, unchanged.
- Stage 3 probe-validation: **14 passed** (13 pre-existing + 1 new).
- Stage 3 match-probe audit: **8 passed** (4 pre-existing + 4 new).
- Stage 3 offload/locking: **6 passed**, unchanged.
- Config: **57 passed**, unchanged.
- Stage 3 matching-service / processing-service: same pre-existing
  Stage 2 `MissingGreenlet` failures as documented in the v2 session
  (6 and 9 respectively) — unrelated to this session's two fixes, not
  re-investigated further.
- `compileall` — clean.
- `ruff check`/`ruff format` on the 5 files touched this session — 3
  findings (all in this session's own new code), fixed; confirmed
  clean afterward.
- No full-suite/global Ruff/mypy pass re-run — v2 session's baseline
  stands; nothing here touches code that baseline covered differently.

No Git operation of any kind occurred in this session.

No Git commit, branch, tag, reset, restore, checkout, clean, or stash
was created or performed this session.


## Correction-patch session — Phase 5 Stage 3 v4

**Status: complete.** Final isolated concurrency correction on top of the
verified Stage 3 v3 ZIP. Stage 4 remains not started.

- Removed request-specific mutation of process-global
  ``PIL.Image.MAX_IMAGE_PIXELS`` from the shared Stage 2/Stage 3 image-validation
  core. Local ``max_pixels``/``max_dimension`` checks now determine each
  request's application limits independently, while Pillow's own process-wide
  bomb guard remains untouched.
- Added a concurrency regression using a 2.5M-pixel image with concurrent 1M
  and 3M request caps: small-cap calls reject, large-cap calls accept, and every
  observed ``Image.open`` sees the unchanged Pillow global threshold.
- Existing v3 empty-scope BLOCKED-audit behavior was not modified.
- Verification: Stage 2 image-validation **13 passed**; Stage 3 probe-validation
  **15 passed**; combined **28 passed**; the new concurrency regression passed
  **5/5** repeated runs; compileall passed. Ruff was unavailable in this
  execution environment and is not claimed as run.
- No migration, Stage 2 service lifecycle, legacy Flask/React code, real
  ``.env``, model artifact, attendance code, or Git state was changed.

## Next task

Phase 5 Stage 4: recognition attendance workflow and APIs, per
`docs/IMPLEMENTATION_PLAN.md` Phase 5 Stage 4's scope and acceptance
criteria — not started in this checkpoint. See
`docs/HANDOVER_PHASE_5_STAGE_3.md`'s "Exact Stage 4 starting point" for
precisely what exists for Stage 4 to build on and what does not yet
exist.

---

## Phase 5 Stage 4 — recognition attendance workflow and APIs

**Status: complete. Stage 5 and Phase 6 not started.**

Delivered the authorized classroom recognition-attempt and explicit
UNKNOWN/AMBIGUOUS confirmation APIs. Candidate UUIDs are derived from active
student profiles after existing attendance-scope authorization; no client
candidate scope or institution-wide fallback exists. FOUND marks PRESENT only
through `AttendanceService`. UNKNOWN/AMBIGUOUS write no attendance until a
locked, re-authorized, roster-checked confirmation. One migration,
`4f8c1a6e92b7` (parent `d22bce264ecd`), adds the safe attempt lifecycle and
roster snapshot without images or embeddings.

Final real-PostgreSQL verification completed on 2026-08-16 against the healthy,
ephemeral Compose `postgres_test` service (PostgreSQL 16; no production/dev
database used). The first run demonstrated and the Stage 4-only correction
fixed overlong explicit migration constraint names; the regression now asserts
all resulting PostgreSQL identifiers fit the server limit. Full migration chain
and final `alembic current` passed at **`4f8c1a6e92b7 (head)`**. The Stage 4
migration round-trip executed and passed **1/1 with no skip**. All five Stage 4
PostgreSQL integration cases executed: **4 passed, 1 Category-B
`MissingGreenlet` failure, 0 skipped**; the failing case had already verified
unrelated-teacher concealment, pre-inference blocking, and no attendance before
the known expired-ORM lookup failed. Phase 4 `AttendanceService`: **24 passed**.
Relevant Stage 3 matching/image-validation/offload/audit: **38 passed, 6
Category-B failures, 0 skipped**. The once-run full backend suite was **625
passed, 47 failed, 0 skipped, 13 warnings**, classified **A=0, B=45, C=2**; no
B/C debt was changed. Scoped Ruff lint/format on all 15 Stage 4 Python files and
`compileall` passed. A fresh test-image build remains blocked by unrelated
Dockerfile missing-CMake debt for `dlib`; it was not changed, and verification
used a disposable extension of the locally cached repository test target. The
known Stage 2 `create_sample` `MissingGreenlet` defect remains unfixed. Full
detail is in `docs/HANDOVER_PHASE_5_STAGE_4.md`.

---

## Phase 5 Stage 5 — runtime closure and hardening

**Status (2026-08-16): complete. Phase 5 complete. Phase 6 not started.**

Started from the locked Stage 4 v2 artifact, whose SHA-256 matched the recorded
`5ec3b280892ad3da5330f39e6142ab359eb9ce121f592ab7dffd57424e49fcea`.
Docker Desktop and the isolated Compose PostgreSQL 16 test service were
reachable; no development or production database was used.

The full empty-database migration chain reached **`4f8c1a6e92b7 (head)`**.
All six migration tests executed and passed, including the Stage 4
`d22bce264ecd → 4f8c1a6e92b7 → d22bce264ecd → 4f8c1a6e92b7` round trip.

Reproduced and fixed the known Stage 2 `MissingGreenlet`: database-side
`updated_at` expiration caused Pydantic response serialization to attempt an
implicit async load after the transaction. The service now refreshes and
serializes inside the active async boundary; replacement/deletion and rollback
compensation were hardened to retain primitive identifiers. A real-PostgreSQL
HTTP regression now proves the safe response path. The no-active replacement
contract now returns the documented 409 conflict. The stale Phase 4 migration
test was corrected to round-trip its historical revision while restoring the
actual Phase 5 head. Other stale test-only assumptions found by the closure
gate were aligned with the existing production contracts.

Added real-PostgreSQL failure/concurrency proof for recognition attendance:
attendance-service failure leaves a persisted, unlinked attempt and zero
partial attendance; retry converges to exactly one attendance state; repeated
or two-session concurrent confirmation is idempotent; a conflicting student
confirmation is rejected without another attendance row.

Final results:

- enrollment/failure-injection/Phase 4 migration correction: **33 passed**;
- former MissingGreenlet fallout plus Stage 3/4 hardening: **36 passed**;
- all migrations: **6 passed, 0 skipped**;
- all Phase 5 plus Phase 4 `AttendanceService`: **217 passed**;
- final affected-files rerun from the freshly rebuilt test image: **62 passed,
  0 skipped**;
- complete backend suite, run once: **675 passed, 0 failed, 0 skipped, 13
  warnings** in 189.61 seconds;
- failure categories after correction: **A=0, B=0, C=0, D=0**;
- `compileall`: passed;
- Ruff format on seven changed Python files: passed; scoped Ruff lint: passed
  except one explicitly unchanged historical Stage 3 test finding;
- strict mypy on the two changed application services: passed;
- full Ruff baseline: 14 old files would reformat and 23 old lint findings;
- full mypy baseline (mypy 1.20.2): 206 errors in 20 historical files, 194
  files checked. No broad cleanup was performed;
- fresh test and production Docker targets built successfully after adding the
  build dependencies required for native dlib compilation;
- live probe: `200 {"status":"alive"}`; ready probe against PostgreSQL:
  `200 {"status":"ready","checks":{"database":"ready"}}`.

Security/release scans found no secret patterns, model weights, biometric
images, or exported embeddings. Matching remains classroom candidate-scoped;
the recognition/provider boundary does not write attendance directly. A real
model smoke test was **not run** because vetted model artifacts were
unavailable; no download and no accuracy claim were made.

Stage 5 changed only:

- `backend_v2/Dockerfile`
- `backend_v2/app/modules/biometric_enrollment/service.py`
- `backend_v2/app/modules/biometric_enrollment/bulk_service.py`
- `backend_v2/app/tests/test_phase5_stage2_enrollment_http.py`
- `backend_v2/app/tests/test_phase5_stage2_failure_injection.py`
- `backend_v2/app/tests/test_migrations_phase4.py`
- `backend_v2/app/tests/test_phase5_stage3_processing_service.py`
- `backend_v2/app/tests/test_phase5_stage4_recognition_attendance.py`
- `backend_v2/README.md`
- `docs/HANDOVER_PHASE_5.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md`

No Git operation was performed. The authoritative closure record is
`docs/HANDOVER_PHASE_5.md`.

---

## Phase 6 — React TypeScript frontend foundation

**Status (2026-08-16): complete. Phase 7 not started.**

Replaced the legacy Create React App/plain-JavaScript frontend with a strict
Vite + React + TypeScript shell. The new root owns one TanStack Query client,
one narrow query-backed auth context, one in-memory access-token store, and one
typed fetch client using `VITE_API_URL`. The backend's rotating refresh token
remains an HttpOnly cookie and is used only through credentialed auth requests.

Protected-request 401 handling is centralized: a single in-flight refresh is
shared, the original request is retried at most once, and refresh failure
clears frontend auth and returns the router to login. Authorization 403
responses are not refreshed. Login uses React Hook Form and Zod, retrieves the
current user through `/auth/me`, and redirects to the matching role shell.

Admin, teacher, and student layouts are non-empty typed components with nested
outlets, identity, navigation, logout, role guards, explicit Phase 7
placeholders, and in-shell wildcard handling. An authenticated-student test
renders `/student/a-future-page` successfully, directly closing the empty
legacy `StudentRoutes.jsx`/`StudentLayout.jsx` runtime failure class.

Final frontend results:

- `npm run typecheck`: passed; the script executes `tsc --noEmit` against all
  source, tests, and Vite configuration;
- `npm run build`: passed with Vite 8.2.1;
- `npm test -- --run`: **2 files, 18 tests passed**;
- `npm run lint`: passed with zero warnings/errors;
- `npm audit`: **0 vulnerabilities** after the compatible transitive
  `fast-uri` security update;
- source audit: no explicit `any`, `@ts-ignore`, broad `eslint-disable`,
  `localStorage`/`sessionStorage`, CRA/react-scripts, axios, auth console
  logging, empty TypeScript modules, or legacy JS/JSX remained.

No backend application, migration, biometric/provider, or Phase 1-5 behavior
was changed. No Git operation was performed. See `docs/HANDOVER_PHASE_6.md`.

---

## Phase 7 - Admin, Teacher, and Student workflows

**Status (2026-08-16): COMPLETE. Phase 8 NOT STARTED.**

Replaced the Phase 6 placeholders with complete role routes and contract-backed
workflows. Admins can manage classrooms, subjects, teacher/student profiles,
classroom membership, assignments, timetable entries, announcements, and
validated CSV/XLSX imports. Teachers can view their server-scoped profile,
classes, subjects, and timetable; mark attendance manually; use camera/file
recognition attendance; and read announcements. Students can view their own
profile, attendance summary/detail with filters, and announcements.

The initial contract audit proved that teachers had no authorized way to obtain
the active classroom `student_profile_id` roster needed by first-time manual
attendance and UNKNOWN/AMBIGUOUS recognition confirmation. After explicit
approval, Phase 7 added the narrow, read-only endpoint
`GET /api/v1/attendance/roster?classroom_id=<uuid>&subject_id=<uuid>`. It
reuses `AttendanceReadService.authorize_scope`, derives active membership on
the server, returns only `student_profile_id` and `roll_number`, performs no
attendance write, exposes no biometric data, and required no migration.

Backend correction verification: focused roster HTTP tests **5 passed**;
roster plus existing attendance regression tests **52 passed**; scoped Ruff,
strict mypy on three changed application files, and compileall all passed.

Frontend verification: `npm run typecheck` passed; `npm run build` passed with
124 modules transformed; `npm test -- --run` passed **6 files / 28 tests**;
`npm run lint` passed; `npm audit --audit-level=high` found **0
vulnerabilities**. The security scan found no browser token/biometric storage,
second transport, scattered fetch client, unsafe logging, `any`, TypeScript
suppressions, institution-wide recognition fallback, FOUND double write, or
camera stream leak.

No Git operation was performed. The authoritative closure record is
`docs/HANDOVER_PHASE_7.md`.

---

## Phase 8 - Reports, exports, and analytics

**Status (2026-08-17): COMPLETE. Phase 9 NOT STARTED.**

Implemented exact-scope attendance reports for Admin and Teacher using the
existing attendance authorization gate. Added bounded month/date-range
attendance summary/detail, active-roster defaulters (including zero-record
students at 0.0%), a deterministic classroom leaderboard, formula-safe CSV,
and bounded multi-page PDF generated entirely in memory. The existing Phase 4
raw attendance CSV endpoint remains unchanged. No migration was required.

Added Admin and Teacher Reports routes, navigation, filters, metrics, tables,
loading/empty/error states, and typed CSV/PDF downloads. Student has no
arbitrary-report route. The same typed API client now handles binary responses
while retaining one 401 refresh/retry and no refresh on 403; report object URLs
are always revoked.

Verification completed against isolated PostgreSQL and local frontend tooling:

- complete backend suite: **706 passed**;
- focused fresh-image reports/attendance set: **48 passed**;
- direct database total matched the report response;
- one-SELECT active-roster aggregate check passed;
- Phase 8-scoped Ruff format/lint passed;
- strict mypy on Phase 8 production files and whole-app compileall passed;
- fresh backend test image built with ReportLab installed;
- frontend typecheck, lint, and production build passed;
- complete frontend suite: **8 files / 40 tests passed**;
- npm audit: **0 vulnerabilities**.

Current-toolchain global Ruff/mypy findings remain documented historical Phase
5 debt and were not broadly rewritten. Security/privacy scans found no new
browser persistence, secondary transport, unsafe logging, temporary export
files, biometric material, credentials, or Student reporting access.

No Git operation was performed. The authoritative closure record is
`docs/HANDOVER_PHASE_8.md`.

---

## Phase 9 — Tests, Docker, CI, deployment, and security closure

**Status (2026-08-17): COMPLETE. Deployable MVP complete. Milestone 2 NOT
STARTED.**

Closed the production-readiness phase without reopening Phases 0–8. The final
runtime is PostgreSQL + FastAPI `backend_v2` + the React/TypeScript/Vite
frontend served by nginx. Production Compose contains a singleton Alembic
migration gate, health-based dependencies, persistent database/biometric
volumes, non-root minimal images, no legacy Flask/Mongo/CRA service, and no
development bind mount or reload server.

Phase 9 added explicit trusted-host validation and a privacy-preserving login
rate limiter, then re-verified original findings C1–C4/H1–H5. The rebuilt v2
findings are closed; historical external-credential rotation and operational
real-model/privacy/calibration work remain explicit human actions rather than
misstated implementation gaps.

Final verification:

- complete PostgreSQL backend suite: **718 passed, 0 failed, 0 skipped, 13
  warnings in 230.80 seconds**;
- Ruff format: **216 files already formatted**; Ruff lint: **all checks
  passed**;
- strict scoped mypy: **success on 129 production files**;
- compileall: **passed**;
- frontend typecheck and lint: **passed**;
- frontend suite: **8 files / 40 tests passed**;
- frontend production build: **passed, 126 modules transformed**;
- standalone npm audit: **0 vulnerabilities**;
- pip-audit after the pytest/pytest-asyncio security update: **no known
  vulnerabilities**;
- fresh migration: base → `4f8c1a6e92b7 (head)`; migration service exited 0;
- production and release-filtered clean-source backend/frontend image builds:
  **passed**;
- clean-source Compose: PostgreSQL, backend, and frontend healthy; frontend,
  live, ready, and proxied API checks passed; and
- secrets/privacy/release scans: no real `.env`, private key, debug dump,
  model weight, biometric artifact, captured image, embedding, or temporary
  report data.

The GitHub Actions workflow now runs backend, frontend, dependency, migration,
static-analysis, test, build, Compose-validation, and production-image jobs.
Hosted CI and a literal independent clone remain post-publication validation
because Phase 9 prohibited all Git operations.

No Git operation was performed. The authoritative closure record is
`docs/HANDOVER_PHASE_9.md`.
