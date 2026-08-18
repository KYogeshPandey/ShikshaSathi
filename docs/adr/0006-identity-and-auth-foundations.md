# ADR 0006: Identity and authentication foundations (Phase 2)

## Status
Accepted

## Context
Rebuild Phase 2 needed to add the first real domain model (`users`) and the authentication/authorization foundation described in `docs/ARCHITECTURE.md` §4–§5 and scoped in `docs/IMPLEMENTATION_PLAN.md` Phase 2. Several concrete decisions were not already settled by earlier documentation and had to be made now: the primary-key strategy, the password-hashing algorithm, the shape of access vs. refresh tokens, refresh-token transport, and CSRF handling for the one cookie-authenticated surface. This ADR records those decisions so they are not silently redesigned later.

## Decisions

### 1. UUID primary keys, not auto-incrementing integers
No earlier document mandated an identifier strategy. Sequential integer IDs make user enumeration trivial once admin/teacher-facing APIs exist (Phase 3) — `/users/2`, `/users/3`, etc. A random UUID primary key removes that enumeration surface for free; the modular-monolith, single-Postgres-instance design (ADR 0004) has no sharding/index-locality reason to prefer integers.

### 2. Argon2id for password hashing, via argon2-cffi
OWASP's current first recommendation for new applications, and a direct upgrade over the legacy app's Werkzeug/scrypt hashing (`docs/AUDIT.md` §2.3 — one thing the legacy app got right, per `docs/LEGACY_MIGRATION_MAP.md`'s "Refactor" decision for Authentication: keep the *approach*, i.e. a modern salted KDF with a safe verification helper, upgrade the *algorithm*). Library defaults are used as-is; Phase 2 does not introduce extra hashing-parameter configuration ("only where genuinely required," per the Phase 2 brief).

### 3. Access tokens: JWT. Refresh tokens: opaque, server-side sessions — not JWT.
Access tokens are short-lived (default 15 minutes), signed JWTs, verified statelessly (signature/expiry/audience/issuer/type), but the resolved user is **always** re-loaded from PostgreSQL before any authorization decision (`app/modules/auth/dependencies.py`) — so a role change or deactivation takes effect on the very next request, not whenever the token happens to expire.

Refresh tokens are deliberately **not** JWTs. They are high-entropy opaque random strings; only a SHA-256 digest is ever persisted, in a new `refresh_sessions` table that also tracks creation/expiry/revocation/rotation lineage. This is what makes real revocation and reuse detection possible: a self-contained JWT refresh token would need its own server-side blacklist to be revocable at all, which is strictly more moving parts for the same result. Reuse of an already-rotated refresh token (its session is revoked *and* has a `replaced_by_id`) is treated as a possible compromise signal: every active session for that user is revoked, forcing re-authentication everywhere.

### 4. Refresh token transport: HttpOnly cookie, scoped to `/api/v1/auth`
Per the Phase 2 brief's default. `Secure` is required whenever `APP_ENV=production` (enforced in `app/core/config.py`); development/testing may relax it since browsers can decline to persist `Secure` cookies over plain `http://localhost`. The cookie's `path` is scoped to the auth router's mount path specifically, so it is never attached to any other endpoint.

### 5. CSRF mitigation: SameSite=Lax + Origin-header allow-list check
The refresh-token cookie's `SameSite=Lax` attribute is the primary defense: browsers do not attach it to cross-site `fetch`/XHR requests or cross-site form POSTs, only to top-level "safe" (GET) navigations. As a second, independent layer, `POST /auth/refresh` and `POST /auth/logout` (the only cookie-authenticated, state-changing endpoints) additionally reject any request whose `Origin` header is present but not in `CORS_ALLOWED_ORIGINS`. A full double-submit CSRF-token scheme was considered and rejected as unnecessary overhead for a JSON-only API with no HTML form endpoints and CORS already restricting credentialed cross-origin `fetch` calls at the browser level.

### 6. JWT signing reuses the existing `SECRET_KEY`; no second secret setting
`SECRET_KEY` already has strong startup validation (minimum length, placeholder rejection — Critical finding C2's fix, Phase 1). Introducing a separate `JWT_SECRET` would be a second, competing secret with no corresponding benefit at this stage, contrary to the Phase 2 brief's instruction to avoid duplicate competing secrets without a documented reason. If access and refresh signing (were refresh tokens ever to become JWTs) needed independent rotation in a later phase, that would be revisited then, not preemptively.

## Alternatives considered
- **Integer PKs with a separate public "slug" or opaque external ID.** Rejected as unnecessary complexity — a UUID PK serves the same purpose with one column, not two.
- **Refresh tokens as JWTs with a `jti` blacklist table.** Rejected: functionally equivalent to the chosen design but with an extra layer of indirection (still need a DB table keyed by session identity; the JWT wrapper around it adds parsing/signature overhead for no additional guarantee, since the DB row is authoritative for revocation either way).
- **Refresh token in the response body (not a cookie), stored by the frontend in memory or `localStorage`.** Rejected: `localStorage` was exactly the legacy app's mistake for the *access* token (`docs/AUDIT.md` §3.4) — any script on the page can read it. An HttpOnly cookie is not readable by JavaScript at all.
- **Full double-submit CSRF token.** Rejected for now as more than this API's actual surface needs (see Decision 5); revisit if a future phase adds an HTML form-based flow.

## Consequences
- `users` and `refresh_sessions` are the first two tables in the v2 schema (`alembic/versions/20260728_..._create_users_and_refresh_sessions.py`).
- Every future protected route depends on `app.modules.auth.dependencies.get_current_active_user` or `require_roles(...)`, giving consistent 401/403 behavior for free.
- Phase 3's admin/teacher/student CRUD endpoints can build directly on `require_roles` and the ownership-check pattern described in `docs/ARCHITECTURE.md` §5, without redesigning authentication.
