# Legacy → v2 Migration Map

Classifications are grounded in `docs/AUDIT.md`. Definitions:
- **Reuse** — logic/approach carries over largely as-is, just re-hosted in the new stack.
- **Refactor** — the concept is right but the implementation needs real changes (bug fixes, security fixes, restructuring).
- **Rewrite** — concept is kept but implementation is built fresh (framework change, or legacy version too thin/broken to adapt).
- **Remove** — not carried forward.
- **Defer** — decision intentionally postponed; not needed for Milestone 1.

| Module / Feature | Current status | Decision | Reason | Target phase |
|---|---|---|---|---|
| Flask application structure (`app/__init__.py` factory) | Working; app-factory pattern, but hardcoded CORS/JWT-secret defaults (AUDIT §2.1, §2.3) | Refactor | The factory-pattern *shape* is worth keeping conceptually (config assembled in one place, extensions registered explicitly) even though the framework changes to FastAPI. The actual insecure defaults do not carry forward. | Phase 1 |
| MongoDB models (`app/models/*.py`) | Working, manual dict-based documents, no schema enforcement at the DB layer | Rewrite | Target stack moves to PostgreSQL + SQLAlchemy 2 models with real constraints/relations. Field names and domain concepts (user roles, classroom/subject/student relations) carry over as reference, not code. | Phase 3 |
| Authentication (login, password hashing) | Working; Werkzeug scrypt hashing, safe login response shape (AUDIT §2.3) | Refactor | The hashing approach and "return only safe fields" pattern are good and should be kept. Everything around it (secret handling, no refresh tokens) needs rebuilding. | Phase 2 |
| JWT utilities (`utils/auth.py`) | Working but duplicated/inconsistent (`requires_roles` vs `token_required`), no object-level checks (AUDIT §2.4, Critical C4) | Rewrite | Two overlapping decorators with different call signatures is exactly the kind of debt not worth porting. New RBAC + ownership-check dependency layer built fresh in FastAPI. | Phase 2 |
| Admin APIs (students/teachers/classrooms/subjects CRUD) | Working, only spot-checked (AUDIT §3.6) | Refactor | Business logic (what fields, what operations) is legitimate and reusable as a spec; implementation moves to FastAPI + Pydantic v2 request/response models. | Phase 3 |
| Teacher APIs | Working, only spot-checked | Refactor | Same reasoning as Admin APIs. | Phase 3 |
| Student APIs | Partially working — backend `/attendance/mystats` exists and looks correct (derives identity from JWT, AUDIT §2.4); **frontend student portal is broken** (Critical C3) | Refactor (backend) / Rewrite (frontend) | Backend self-service pattern is exactly right and worth keeping. Frontend has nothing working to reuse — `StudentRoutes.jsx`/`StudentLayout.jsx` are empty. | Phase 3 (backend), Phase 6–7 (frontend) |
| Attendance | Working end-to-end at the API level, but missing object-level authorization (Critical C4) and has no audit trail beyond `marked_by` | Refactor | Domain logic (bulk save, stats, detail, export) is sound; this becomes the reference spec for Phase 4. Authorization must be added, not just ported. | Phase 4 |
| Timetable | Working (`models/timetable.py` populated, route uses `token_required`); `services/timetable_service.py` is dead/empty and unused | Refactor | Real logic exists in the model layer; the empty service file is noise, not a gap. Fold model logic into the new service/repository layer. | Phase 3 |
| Announcements | Working (`models/announcement.py` populated); `services/announcement_service.py` is dead/empty and unused | Refactor | Same pattern as Timetable. | Phase 3 |
| Reports | Working, only spot-checked (`api/v1/reports.py` referenced from frontend: `fetchAttendanceReport`, `fetchClassroomLeaderboard`, `fetchDefaultersList`) | Refactor | Not deeply audited in this pass (see AUDIT §2.10 note on scope); revisit specifics at Phase 3/8 kickoff rather than assume. | Phase 8 |
| Audit logs | Working feature (`services/audit_log_service.py`, `models/audit_log.py`, `AuditLogPage.jsx`) — note this is unrelated to this rebuild's own `docs/AUDIT.md` process, just a same-named in-app feature | Refactor | Legitimate feature worth keeping; needs to broaden coverage once real object-level authorization exists (Phase 4), so failed/blocked authorization attempts can be logged too. | Phase 4 |
| CSV / Excel import-export | Working but unguarded (AUDIT §2.10 — no try/except, no row caps) | Refactor | Keep the pandas-based approach; add validation, row limits, and per-row error reporting. | Phase 3 / Phase 8 |
| Face detection | **Not implemented** — `ml/detector.py` is empty (AUDIT §2.13, High H3) | Rewrite | Nothing to migrate. Module boundary (`detector` → `embedder` → `matcher`) is a reasonable shape to keep conceptually. | Phase 5 |
| Face embedding / matching | **Not implemented** — `ml/embedder.py`, `ml/matcher.py` empty | Rewrite | Same as above; provider choice is genuinely open — see `docs/adr/0005-face-recognition-provider-pending.md`. | Phase 5 |
| React application shell (`App.jsx`, routing) | Working for Admin/Teacher, broken for Student (Critical C3) | Rewrite | Full frontend moves to React + TypeScript + Vite per target architecture; legacy CRA shell is a reference for route structure and role-splitting, not code to port directly. | Phase 6 |
| Role dashboards (Admin/Teacher/Student) | Admin & Teacher working; Student broken (empty routing/layout) | Rewrite | Dashboards rebuilt in TypeScript against the new API contracts; legacy versions used as UX reference only. | Phase 7 |
| API client (`src/api/api.js`) | Working, centralized axios instance, token attached via interceptor (AUDIT §3.3) | Refactor → Rewrite | Centralization pattern is good; concrete implementation becomes a typed client (TanStack Query + generated or hand-written types) since axios-with-manual-endpoints doesn't carry over 1:1 into TypeScript. | Phase 6 |
| Routing | Admin/Teacher patterns reusable as reference; Student route is empty (Critical C3) | Rewrite | New React Router setup written against TypeScript route/page structure. | Phase 6 |
| Tailwind styling | Working, configured via `tailwind.config.js` + PostCSS | Reuse | Tailwind carries forward directly into the Vite-based frontend; config needs adapting from CRA's build pipeline to Vite's, not a conceptual change. | Phase 6 |
| Tests (backend & frontend) | **Not implemented** — all backend test files empty (AUDIT §2.12); no frontend tests exist at all | Rewrite | Nothing to migrate; written fresh against the new stack (pytest for FastAPI, Vitest/RTL for the frontend). | Phase 9 (with earlier smoke tests recommended in Phase 1/2, per AUDIT §2.12) |
| README / API docs | Present but describes a different stack than what's implemented (AUDIT §4.1 — Vite claimed, CRA actual; face-api.js/TensorFlow.js claimed, OpenCV/MTCNN-shaped-but-empty actual) | Rewrite | Superseded by `docs/ARCHITECTURE.md` and a corrected README at the end of the rebuild. | Phase 9 |
| Deployment scripts | **Not present** — no Dockerfile, no docker-compose, no CI workflow (AUDIT §4.4–§4.6) | Defer | Nothing to migrate; new Docker Compose setup is a Phase 1 deliverable per the target architecture, full CI in Phase 9. | Phase 1 (dev compose) / Phase 9 (CI) |

---

### Explicitly deferred decisions

- **Face-recognition provider** (which library/service to standardize on) — deferred; see `docs/adr/0005-face-recognition-provider-pending.md`. Evaluation criteria are documented there, no selection made yet.
- **Whether to keep MongoDB as a secondary store for biometric artifacts** vs. fully moving to PostgreSQL + object storage — deferred to Phase 5 when the face-recognition provider is chosen, since that choice affects storage shape.
