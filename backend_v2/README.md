# ShikshaSathi backend_v2

`backend_v2` is the production FastAPI/PostgreSQL backend for the ShikshaSathi
Deployable MVP. It replaces the historical Flask/MongoDB application under
`../backend`, which is retained as source history but is absent from the
production startup topology.

## Stack and modules

- Python 3.12, FastAPI, Pydantic Settings
- async SQLAlchemy 2, asyncpg, PostgreSQL 16, Alembic
- Argon2id password hashing, JWT access tokens, rotating opaque refresh sessions
- structured logging and request correlation
- academic/profile/announcement/import modules
- transactional attendance and immutable audit logs
- secure biometric enrollment plus YuNet/dlib recognition pipeline
- bounded reports with formula-safe CSV and in-memory PDF
- pytest, Ruff, and strict scoped mypy

Application source is in `app/`, migrations in `alembic/`, administrative
commands in `scripts/`, and tests in `app/tests/`.

## Security boundary

`Settings` is the only runtime configuration source. `SECRET_KEY`,
`DATABASE_URL`, and PostgreSQL credentials have no fallback. Production startup
rejects debug mode, wildcard/empty CORS, wildcard/empty trusted hosts, and a
non-Secure refresh cookie.

The login endpoint has a process-local fixed-window limiter (default: five
attempts per 60 seconds per client address). The production image intentionally
runs one Uvicorn worker. A horizontally scaled deployment must replace this
with a shared limiter at the trusted ingress.

Access tokens are short-lived and held by the frontend in memory. Refresh
tokens are opaque, hashed in PostgreSQL, rotated on use, and transported only in
an HttpOnly, Secure, path-scoped cookie. Roles are loaded from PostgreSQL on
each request. Attendance and reports verify the exact active
teacher/classroom/subject assignment; student self-service derives identity
from the authenticated user.

Unexpected errors are client-sanitized. Logs do not receive request bodies,
authorization/cookie headers, passwords, tokens, database URLs, image bytes,
embeddings, or model paths.

## Local setup

Use Python 3.12+ and a dedicated PostgreSQL database:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

`backend_v2/.env.example` targets standalone development. The root
`.env.example` is the production Compose template.

Create the first admin after migrations:

```bash
python -m scripts.bootstrap_admin
```

The password is prompted without echo. There is no public registration route.

## Migrations

```bash
alembic history
alembic upgrade head
alembic current
```

Production Compose uses a one-shot `migrate` service and blocks backend startup
until `alembic upgrade head` succeeds. Downgrades are deliberately manual and
must follow a backup/review decision.

## Health

- `GET /health/live`: liveness only; does not touch PostgreSQL.
- `GET /health/ready`: real `SELECT 1`; returns 503 with a sanitized envelope
  when PostgreSQL is unavailable.

The runtime image also uses readiness as its container health check.

## API

All business routes are under `/api/v1`. The implemented route inventory,
role/scope rules, upload limits, and report filters are documented in
`../API_DOCS.md`. OpenAPI is generated at `/openapi.json` with Swagger UI at
`/docs`.

## Recognition configuration

Recognition code is implemented but disabled by default with
`FACE_RECOGNITION_PROVIDER=none`. Enabling `server_side_local` requires
deployer-supplied YuNet `.onnx` and dlib `.dat` paths and identifiers; optional
SHA-256 settings verify them before load. Model weights are never bundled in
source, images, or release ZIPs.

The default cosine threshold (`0.82`) is provisional, not classroom-calibrated,
and no accuracy claim is made. The MVP has no liveness detection. See
`../docs/BIOMETRIC_DATA_POLICY.md` and ADR 0011 before enabling recognition.

## Quality gates

With a migrated isolated PostgreSQL test database configured:

```bash
pytest
ruff format --check app alembic scripts
ruff check app alembic scripts
mypy app --exclude 'app/tests'
python -m compileall -q app alembic scripts
```

From the repository root, the test profile provisions a separate ephemeral
database:

```bash
docker compose --profile test up -d postgres_test
docker compose --profile test run --rm backend_v2_test
```

The multi-stage Dockerfile keeps native dlib compilation in the builder. The
runtime has production dependencies only, runs as UID/GID 1000, starts Uvicorn
without reload, and contains neither tests nor build tools.

## Proxy and host trust

The shipped Compose topology does not publish the backend port. Nginx is the
only ingress on the private network, so Compose sets `FORWARDED_ALLOW_IPS=*`
for Uvicorn and forwards the original client chain. If the backend is exposed
or an ingress is added, restrict this to exact proxy addresses. Independently,
`TRUSTED_HOSTS` must contain only the public host names accepted by the app.
