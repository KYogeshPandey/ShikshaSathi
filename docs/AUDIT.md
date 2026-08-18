# ShikshaSathi — Repository Audit (Rebuild Phase 0)

**Scope:** Legacy Flask + MongoDB + React (CRA) codebase, as delivered in `ShikshaSathi.zip`.
**Method:** Direct inspection of source files, `git log`/`git status`, dependency manifests, and a full-repo `py_compile` syntax sweep. No dependencies were installed (sandbox has no network egress — see `docs/PROGRESS.md` → "Commands run" for exact attempts and failures), so no live server, no `pytest` run, and no frontend build/test run were possible. Every finding below is traceable to an exact file and, where useful, an exact line.
**Not claimed:** this is not an exhaustive line-by-line review of every route/component. It is a grounded first pass that prioritizes security, correctness of the running app, and anything that would mislead a rebuild. Areas only spot-checked are marked as such.

---

## Executive summary — Critical & High findings

| # | Severity | Area | Finding |
|---|----------|------|---------|
| C1 | Critical | Repo state / secrets | Live MongoDB Atlas credential was written to disk in plaintext via a debug `print()` and captured in two now-removed root files |
| C2 | Critical | Backend auth | JWT signing secret has an insecure hardcoded fallback (`"change_this_in_env"`) |
| C3 | Critical | Frontend routing | Student portal (`/student/*`) is wired to an **empty** route file and **empty** layout — guaranteed runtime crash for any student login |
| C4 | Critical | Backend authorization | No object-level authorization on attendance endpoints — any authenticated teacher can read/write attendance for classrooms they are not assigned to |
| H1 | High | Backend | No rate limiting anywhere in the app, including `/auth/login`, despite `flask-limiter` being a declared dependency |
| H2 | High | Backend | Zero real test coverage — all 5 test files exist but are empty |
| H3 | High | Backend / ML | Face recognition is entirely unimplemented (`detector.py`, `embedder.py`, `matcher.py` are all empty, never imported) despite being the headline feature in `README.md` |
| H4 | High | Backend | Bulk photo import (`extract_photos`) has a zip-slip-pattern weakness: a sanitized filename is computed but the **unsanitized** entry name is what actually gets extracted |
| H5 | High | Backend | CORS allows all origins (`origins: "*"`) on every `/api/*` route |

Full detail for these and all Medium/Low findings follows, grouped by area as requested.

---

## 1. Repository state

### 1.1 Dirty working tree — **Medium**, evidence-based, not a defect in the app itself
- **Evidence:** `git status --short` against `HEAD` (`c64fa9b`) shows **90 modified files, 5 deleted files, 5 untracked files** in the ZIP as delivered.
- **Risk:** the ZIP is not a reproducible snapshot of any commit. Any diff, blame, or "what changed" question must be answered against the working tree, not the last commit.
- **Fix:** documented in `docs/PROGRESS.md`. No files were reset or discarded (per Phase 0 constraints). Recommend the next session in this line of work commits or explicitly re-baselines before Phase 1 starts.
- **Target phase:** Rebuild Phase 0 (documentation only, done here).

### 1.2 Embedded `.git` history — **Medium**
- **Evidence:** `.git/` present, 12 commits, branch `main`, remote `github.com/KYogeshPandey/ShikshaSathi.git`.
- **Risk:** none by itself (this is real project history and should be kept). The risk is operational: this ZIP includes the full `.git` folder, so **it must not be redistributed or uploaded elsewhere as-is** without considering that history is included.
- **Fix:** none required now. Documented so future shareable exports use `git archive` or explicitly strip `.git`.
- **Target phase:** N/A (informational).

### 1.3 Generated files (caches) — **Low**, now cleaned
- **Evidence (before cleanup):** 14 `__pycache__/` directories, 113 `.pyc` files (some of that count is from tooling run during this audit itself, e.g. a syntax-check sweep; the rest pre-existed).
- **Fix:** removed in this session. See §3 and `docs/PROGRESS.md`.
- **Target phase:** Rebuild Phase 0 (done).

### 1.4 Debug files containing a live secret — **Critical (C1)**
- **Evidence:** `debug_output.txt` and `debug_output_safe.txt` (both untracked, UTF-16 encoded) each contained a single line: a full MongoDB Atlas SRV connection string **including a plaintext username and password**. Root cause traced to `backend/app/core/db.py`, which contains `print("DEBUG MONGODB_URI:", uri)` immediately after reading `MONGODB_URI` from the environment — every local run of the app prints the live credential to stdout, and someone had redirected that output to these two files.
- **Also related:** `debug_result.txt` (untracked) contained the **first 10 characters of real `password_hash` values** for users in the database, produced by `backend/debug_db.py` (see §3.2 for that script's disposition).
- **Risk:** credential exposure. Because the value was written to disk and included in this ZIP, it must be treated as exposed regardless of whether it was ever committed to git (it was not — confirmed via `git log --all -p`, zero matches).
- **Recommended fix:** **rotate the MongoDB Atlas password immediately**, independent of rebuild phasing. Remove the `print("DEBUG MONGODB_URI", ...)` line from `core/db.py` (left in place in this phase — see Constraints; this is a one-line source change, flagged here for immediate human action or as the first Phase 1 task). The three files have been deleted from the working tree in this session (§3.1) and `.gitignore` now blocks the pattern from recurring (§3.3).
- **Target phase:** Immediate (credential rotation) + Phase 1 (remove the print statement, introduce structured logging that never logs secrets).

### 1.5 Empty / placeholder modules — **Low–High depending on module** (see Backend/Frontend sections for the ones that matter functionally: `ml/*`, all `tests/*`, `routes/StudentRoutes.jsx`, `layout/StudentLayout.jsx`)
- **Evidence (full inventory):**
  Backend: `middleware/auth_middleware.py`, `services/timetable_service.py`, `services/announcement_service.py`, `migrations/README.md`, all 5 files under `tests/`, all 4 files under `ml/`.
  Frontend: `routes/StudentRoutes.jsx`, `layout/StudentLayout.jsx`, `layout/DashboardLayout.jsx`, `hooks/useAuth.js`, `components/timetable/TimetableGrid.jsx`, `components/notices/NoticeBoard.jsx`, `components/notices/CreateNoticeModal.jsx`, `utils/constants.js`, `utils/formatters.js`, `utils/storage.js`.
- **Risk:** varies — most are genuinely dead/unreferenced (Low), two are load-bearing and broken (see C3, H2, H3).
- **Fix:** see individual findings below; full list carried into `docs/LEGACY_MIGRATION_MAP.md`.
- **Target phase:** mixed, see migration map.

### 1.6 Deleted files (relative to `HEAD`) — **Low**
- **Evidence:** `frontend/src/App.css`, `App.test.js`, `logo.svg`, `main.jsx`, `setupTests.js` — all Create React App boilerplate defaults.
- **Risk:** none observed; looks like intentional CRA boilerplate cleanup (removing the default CRA test/entry files in favor of the project's own `App.jsx`/`index.js`).
- **Fix:** none needed.
- **Target phase:** N/A.

### 1.7 Stale tracked files — **Low**
- `migrations/README.md` — tracked, 0 bytes. Placeholder that was never filled in; there is no real migration tooling for MongoDB (matches §2.9 below).
- **Target phase:** superseded entirely by the Postgres/Alembic migration approach in Rebuild Phase 1.

### 1.8 Missing environment template — **Medium**, now fixed
- **Evidence:** no `.env.example` existed; only two env vars are read anywhere in the backend (`MONGODB_URI`, `JWT_SECRET`) and one in the frontend (`REACT_APP_API_URL`) — confirmed by grep across the full source tree.
- **Fix:** `backend/.env.example` created in this session (§4). Grouped per the brief; variables beyond the three above are explicitly marked as reserved/not-yet-wired, so the file doesn't imply configurability that doesn't exist yet.
- **Target phase:** Rebuild Phase 0 (done) / Phase 1 (actually wire up the reserved groups: CORS origin allow-list, rate-limit config, upload limits).

---

## 2. Backend (Flask)

### 2.1 App factory & modularity — **Low / informational**
- **Evidence:** `backend/main.py` → `create_app()` in `backend/app/__init__.py`. Reasonably modular layout: `api/v1`, `core`, `models`, `schemas`, `services`, `middleware`, `ml`, `migrations`, `tests`, `utils`.
- **Assessment:** the factory pattern itself is sound and worth keeping conceptually in the FastAPI rebuild (as a dependency-injection root), even though the framework changes.

### 2.2 MongoDB configuration — **Critical (C1) + Medium**
- Debug print of the credential: see §1.4.
- **Medium — silent failure:** `init_db()` catches all connection exceptions, logs with `print()`, and sets `app.config["db"] = None` rather than failing fast. The app will start "successfully" even with no working database; every subsequent request that touches `get_db()` will instead fail at call time with a generic `RuntimeError`. `/health` does not check DB connectivity, so it will report `{"status": "ok"}` even when Mongo is unreachable.
  - **Fix:** fail fast on startup in production, or make `/health` reflect real DB state.
  - **Target phase:** Phase 1 (this class of problem goes away with SQLAlchemy's connection handling, but the fail-fast health-check pattern should be carried forward deliberately).

### 2.3 Authentication — **Critical (C2) + Medium**
- **C2:** `app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET", "change_this_in_env")` in `backend/app/__init__.py`. If `JWT_SECRET` is ever unset (e.g., a misconfigured deploy), the app silently signs tokens with a value visible in the public source tree, and anyone can forge a valid admin token.
  - **Fix:** raise at startup if `JWT_SECRET` is missing; never ship a fallback secret.
  - **Target phase:** treat as immediate; formal fix ships in Phase 2 (Auth/RBAC) of the rebuild.
- **Medium — no refresh-token flow:** `backend/app/api/v1/auth.py` issues only a single `create_access_token(...)`, no `create_refresh_token`. Combined with no explicit `JWT_ACCESS_TOKEN_EXPIRES` in the factory, sessions rely entirely on the flask-jwt-extended library default. There's no way to revoke or rotate a token short of changing the secret.
  - **Target phase:** Rebuild Phase 2 ("refresh-token security" is already the stated goal for that phase).
- **Positive finding:** `auth_service.authenticate()` returns only safe public fields (`id`, `username`, `role`, `email`, `name`) — `password_hash` is never sent to the client. Login input is normalized/stripped before lookup.

### 2.4 JWT handling / RBAC / object-level authorization — **Critical (C4) + Medium**
- **Evidence:** `backend/app/utils/auth.py` defines two parallel, overlapping decorators:
  - `requires_roles(*roles)` — checks `claims.get("role")` against an allow-list.
  - `token_required` — a second, differently-shaped decorator (its own comment describes it as a compatibility wrapper added later for routes expecting a `current_user` argument).
  Both independently call `verify_jwt_in_request()`; several routes stack `@jwt_required()` *and* `@requires_roles(...)` together, which is redundant (the latter already verifies the token).
  `backend/app/middleware/auth_middleware.py` — the file the name implies should hold this logic — is empty; all of it actually lives in `utils/auth.py` as decorators instead.
- **C4 — no object-level authorization:** every route in `backend/app/api/v1/attendance.py` (`/stats`, `/daily`, `/detail`, `/export`, `/manual`) accepts `classroom_id` from the query string or POST body and passes it straight to the service layer with **no check that the authenticated teacher is actually assigned to that classroom**. Any valid teacher JWT can read or write attendance for any class in the system by changing an ID. `/mystats` is the one endpoint that gets this right — it derives `student_id` from the JWT identity rather than trusting client input — which shows the pattern is known in this codebase, just not applied consistently.
  - **Fix:** add ownership checks (teacher↔classroom assignment, or admin override) before any read/write in the service layer, not just role checks.
  - **Target phase:** Rebuild Phase 2 ("ownership checks" is already called out as a Phase 2 deliverable) — this finding is the concrete justification for it.
- **Medium — information disclosure:** both decorators return `str(e)` from a bare `except Exception` directly in the JSON response body, which can leak internal exception text to API clients.
  - **Target phase:** Phase 2.

- **Rebuild mitigation status (2026-08-01) - CLOSED for `backend_v2`:**
  every attendance write, detail read, daily read, statistics query,
  and CSV export passes through service-layer scope authorization.
  Teachers must have an active teacher profile and active
  teacher-classroom-subject assignment; admins have the documented
  override. Unrelated teacher access is concealed as `404` and the
  blocked attempt is persisted as an independent audit-log record.
  Service and HTTP coverage passed in the final 311-test PostgreSQL
  suite, including successful and blocked audit visibility.
- **Legacy qualification:** the original Flask/Mongo implementation
  described above remains unchanged and retains this finding until
  it is retired. The closure applies to the rebuilt FastAPI backend.
### 2.5 CORS — **High (H5)**
- **Evidence:** `CORS(app, resources={r"/api/*": {"origins": "*", ...}})` in `backend/app/__init__.py`.
- **Risk:** any website can call the API from a browser. Mitigated somewhat by the app using `Authorization: Bearer` tokens rather than cookies (so it's not classic CSRF), but it still allows any origin to attempt credentialed requests if a token is available to their script, and it's simply not appropriate for a production deployment handling student data.
- **Fix:** restrict to an explicit allow-list (`CORS_ALLOWED_ORIGINS`, already stubbed in `.env.example`).
- **Target phase:** Phase 1/2.

### 2.6 Rate limiting — **High (H1)**
- **Evidence:** `flask-limiter==3.5.0` is in `requirements.txt`; `grep -rn "Limiter"` across the entire backend returns zero matches. It is never instantiated or applied anywhere.
- **Risk:** `/api/v1/auth/login` has no throttling at all — open to credential stuffing / brute force.
- **Fix:** wire up `flask-limiter` (legacy) or the FastAPI-side equivalent (rebuild), starting with the login route.
- **Target phase:** urgent enough to consider a legacy hotfix; formally scheduled in Rebuild Phase 2.

### 2.7 Error handling & logging — **Medium**
- **Evidence:** app-level handlers exist only for 404/500 (`backend/app/__init__.py`). Every route file wraps its body in `try/except Exception as e: print(f"❌ ...: {e}")`. There is no use of Python's `logging` module anywhere in the backend — all diagnostic output goes to `print()`, which is not persisted, not leveled, and not structured.
- **Fix:** introduce real logging (module-level loggers, log levels, no secrets in log lines — directly relevant given §1.4) as part of the FastAPI rebuild's cross-cutting concerns.
- **Target phase:** Phase 1 (foundation) / Phase 4 (audit trail specifically for attendance actions).

### 2.8 Validation — **Low–Medium**
- **Evidence:** Pydantic v2 schemas exist under `backend/app/schemas/` (spot-checked `attendance_schema.py` — a clean, minimal `AttendanceCreate` model). Not confirmed whether every route actually validates incoming JSON through these schemas versus reading `request.get_json()` directly (several routes observed do the latter, e.g. `attendance.py`, `timetable.py`, `announcements.py`).
- **Fix:** confirm/standardize schema validation on every write endpoint.
- **Target phase:** Phase 3 (this is exactly what Pydantic + FastAPI's request models solve structurally).

### 2.9 Database failure behavior / demo or fallback data — **Low**
- Covered in §2.2 (silent failure). No evidence of hardcoded "demo data" fallbacks in the backend itself (unlike the frontend — see §3 mismatch with `README.md`'s stated "Demo data + basic structure" plan for AI Phase 1, which was never built at all rather than stubbed with fake data).

### 2.10 CSV / Excel handling — **Medium** (spot-checked, not exhaustive)
- **Evidence:** `backend/app/utils/file_upload.py` → `process_student_excel` / `process_teacher_excel` call `pd.read_excel()` directly with no try/except, no row-count cap, and no schema validation beyond ad hoc dict construction per row.
- **Risk:** a malformed upload throws an unhandled exception up to the generic 500 handler; there's no cap on rows/size, so a very large file could be a resource-exhaustion vector.
- **Fix:** wrap in explicit validation with row limits and clear per-row error reporting.
- **Target phase:** Phase 3 (Academic domain APIs) / Phase 8 (bulk import UX).

### 2.11 File uploads (images) — **High (H4) + Low**
- **H4 — zip-slip pattern:** `extract_photos()` computes `filename = secure_filename(file)` for the eventual on-disk name, but calls `zf.extract(file, dest_folder)` using the **raw, unsanitized** entry name from the zip — the sanitized name is only used in the follow-up `os.rename()`. Python's `zipfile.extract` has some built-in protection against absolute paths, but the code does not explicitly validate each entry (reject `..` components, absolute paths, or unexpected nesting) before extraction, so it is relying on stdlib defaults rather than an explicit check.
  - **Fix:** validate every entry name before calling `extract`; reject anything that doesn't resolve inside `dest_folder`.
  - **Target phase:** Phase 5 (face enrollment / bulk photo import is exactly where this code is used).
- **Low:** the image-validation step uses a bare `except:` that silently deletes files that fail `Image.open().verify()` with no logging of which file or why.

### 2.12 Tests — **High (H2)**
- **Evidence:** `backend/app/tests/unit/{test_classroom_service,test_attendance_service,test_auth_service}.py` and `backend/app/tests/integration/{test_attendance_integration,test_auth_integration}.py` — all five files are 0 bytes. `pytest==7.4.3` is a declared dependency. A sensible `unit/`/`integration/` split exists structurally, but there is no test code to run. (`pytest` itself is also not installed in this audit sandbox — could not attempt a collection run; recorded as a failed/unavailable check in `docs/PROGRESS.md`.)
- **Fix:** this is a from-scratch test-writing effort, not a repair.
- **Target phase:** Rebuild Phase 9 formally, but recommend lightweight smoke tests earlier (Phase 1/2) given how much of this audit had to be done by reading code rather than running any verification suite.

### 2.13 Face-recognition implementation — **High (H3)**
- **Evidence:** `backend/app/ml/{__init__.py, detector.py, embedder.py, matcher.py}` are all 0 bytes. `grep` across the entire backend for `cv2`, `mtcnn`, `MTCNN`, `face_recognition` returns no matches outside `requirements.txt` — the module is never imported by anything.
- **Assessment:** despite `README.md` presenting face-recognition attendance as the headline feature, **none of it is built**. This is good news for the rebuild in one sense — there is no legacy face-recognition logic to migrate or reverse-engineer, only a clean module boundary (`detector` → `embedder` → `matcher`) that was scaffolded but never filled in, which is a reasonable shape to reuse conceptually.
- **Target phase:** Rebuild Phase 5, effectively a greenfield build. See `docs/adr/0005-face-recognition-provider-pending.md`.

---

## 3. Frontend (React / Create React App)

### 3.1 Create React App status — **Low / informational**
- **Evidence:** `react-scripts@5.0.1`, standard CRA `start`/`build`/`test`/`eject` scripts in `package.json`. `README.md` states the frontend uses **Vite** — it does not (see §4.1).

### 3.2 React Router usage & role-based routing — **Critical (C3)**
- **Evidence:** `src/App.jsx` mounts three role sections: `AdminRoutes`, `TeacherRoutes`, `StudentRoutes`, each behind `ProtectedRoute`. `AdminRoutes.jsx` and `TeacherRoutes.jsx` are fully implemented. **`src/routes/StudentRoutes.jsx` is 0 bytes** — it has no default export — yet `App.jsx` does `import StudentRoutes from "./routes/StudentRoutes"` and renders `<StudentRoutes />` at `/student/*`. `src/layout/StudentLayout.jsx` is also 0 bytes.
- **Risk:** this is not a "gap," it's a guaranteed runtime error. Any user who logs in with role `student` and is routed to `/student/*` will hit React's "element type is invalid" crash, because the default export `StudentRoutes` resolves to `undefined`. `StudentDashboard.jsx` (the page component) and the backend's `/attendance/mystats` endpoint both exist and are ready to be used — only the routing/layout glue is missing.
- **Fix:** implement `StudentRoutes.jsx` and `StudentLayout.jsx` following the same pattern as `TeacherRoutes.jsx`/`TeacherLayout`.
- **Target phase:** flagged here because it affects how "done" the legacy app actually is; formally rebuilt in Phase 6/7 (React TypeScript frontend + Student workflow) rather than patched in the legacy JS app, per Phase 0 constraints (no frontend rewrite in this phase).

### 3.3 API integration — **Low / informational**
- **Evidence:** `src/api/api.js` — a single centralized axios instance with a request interceptor that attaches `Authorization: Bearer <token>`. Endpoint list is broad and matches most backend blueprints (auth, students, teachers, classrooms, subjects, attendance, reports, timetable, announcements).
- **Assessment:** reasonable centralization; worth keeping conceptually as a single typed API client in the rebuild (TanStack Query wrapping a generated or hand-written client).

### 3.4 Token storage — **Medium**
- **Evidence:** JWT is stored in `localStorage` (`src/api/api.js` reads it directly; `src/context/AuthContext.jsx` also reads/writes `localStorage` for both `token` and `user` independently — two separate code paths touching the same storage key rather than one source of truth).
- **Risk:** `localStorage` is readable by any script on the page, so this is the standard XSS-exposes-the-token trade-off (common in SPAs, but worth calling out explicitly since this app handles student data). There is also no 401-response interceptor — an expired/invalid token is not automatically detected or cleaned up; the user just gets failed requests.
- **Fix:** in the rebuild, evaluate httpOnly cookie storage or at minimum add a response interceptor that clears auth state and redirects to `/login` on 401.
- **Target phase:** Rebuild Phase 2 (frontend half of the auth work) / Phase 6.
- **Minor:** `AuthContext.logout()` also clears `erpRole`/`erpUserName` localStorage keys that are not set anywhere else in the current codebase — likely leftover from an earlier naming convention, harmless but worth a note.

### 3.5 Role-based routing — see §3.2 (Critical finding covers this).

### 3.6 Hardcoded / demo data — **not exhaustively checked**
- Spot-checked `App.jsx`, `AuthContext.jsx`, `api.js`, `ProtectedRoute.jsx`, all three role route files. No hardcoded demo datasets found in these files. Individual page/component bodies (17 page components, dozens of smaller components) were **not** all opened in this pass — flagged as an area for a follow-up pass rather than claimed clean.

### 3.7 Large components / loading-error-empty states / accessibility / responsiveness / test quality — **not checked in this pass**
- Frontend has no test files at all under `src/` (only the CRA-default `App.test.js`, which was deleted per §1.6, and nothing replaced it) — consistent with the backend's zero-test-coverage finding (§2.12), so it's fair to say frontend test quality is "none" with high confidence even without opening every component. Accessibility, responsiveness, and component-size review were not performed — out of scope for the time available in this pass; recommended as an explicit early Phase 6/7 task rather than assumed.

### 3.8 Build consistency — **Low**
- `package-lock.json` is present and tracked, which is good practice for reproducible installs. Could not run a real `npm install`/`npm run build` in this sandbox (no network egress — see `docs/PROGRESS.md`).

---

## 4. Documentation and deployment

### 4.1 README accuracy — **Medium**
- **Evidence:** `README.md` states the frontend stack as **"React + Vite."** The actual `frontend/package.json` uses **Create React App (`react-scripts`)**, not Vite. `README.md` also describes the AI/face-recognition approach as **"Demo data + basic structure"** for an initial phase and **"face-api.js / TensorFlow.js in browser"** for a later optional phase; the actual (unimplemented) code takes a different approach entirely — a backend Python pipeline using OpenCV + MTCNN (per `requirements.txt` and the empty `ml/` module shape), not an in-browser JS model.
- **Risk:** README describes an earlier or aspirational plan, not the code as it exists. Anyone onboarding from the README alone will have an incorrect mental model of both the frontend build tool and the face-recognition approach.
- **Fix:** README will be superseded by `docs/ARCHITECTURE.md` for the rebuild; the legacy README should be updated or clearly marked "legacy" rather than left as the primary onboarding doc.
- **Target phase:** Rebuild Phase 0 follow-up / Phase 9 (final docs pass).

### 4.2 API_DOCS accuracy — **not verified against live server**
- 323 lines, present at root. Could not be verified against a running server (no dependencies installable in this sandbox). Spot-checking its claims against the actual route files is recommended as an early Phase 1 task rather than assumed accurate.

### 4.3 Environment setup — **Medium**, addressed
- No `.env.example` existed before this session (§1.8). Now created at `backend/.env.example`.

### 4.4 Docker readiness — **Low**
- No `Dockerfile` or `docker-compose.yml` found anywhere in the repository (`find . -iname "Dockerfile*" -o -iname "docker-compose*"` — no matches, checked during this audit). Rebuild architecture targets Docker Compose from Phase 1 onward; this is a from-scratch addition, not a repair.

### 4.5 CI readiness — **Low**
- No `.github/workflows/` directory exists. From-scratch addition, scheduled for Rebuild Phase 9.

### 4.6 Deployment readiness — **Medium**
- `gunicorn` is a declared backend dependency (suggesting some deployment intent) but no `Procfile`, gunicorn config, or WSGI entry beyond `backend/main.py`'s `app.run(debug=True)` (development server, not production-appropriate) was found. Given §2.3/§2.5/§2.6 (default JWT secret, open CORS, no rate limiting), the app is **not deployment-ready as-is** regardless of process-management tooling.

---

## Dependency notes (cross-cutting, Low severity)

Declared in `backend/requirements.txt` but confirmed **unused** anywhere in the codebase:
- `bcrypt` — password hashing actually uses Werkzeug's `generate_password_hash`/`check_password_hash` (scrypt-based), not bcrypt directly.
- `flask-limiter` — never instantiated (§2.6).
- `opencv-python`, `mtcnn` — face recognition unimplemented (§2.13).

None of these are insecure by being unused — they're just dead weight in `requirements.txt` that overstates what the app actually does. Recommend trimming or, better, treating this list as the "intent" list that Rebuild Phase 5 will actually fulfill.

---

*Findings in this document are the basis for `docs/LEGACY_MIGRATION_MAP.md`, `docs/ARCHITECTURE.md`, and `docs/IMPLEMENTATION_PLAN.md`. See `docs/PROGRESS.md` for exactly which commands were run to produce this audit and which checks could not be run in this environment.*
