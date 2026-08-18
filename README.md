# ShikshaSathi

ShikshaSathi is a role-based school attendance system with a FastAPI/PostgreSQL
backend and a React/TypeScript frontend. It supports academic administration,
manual attendance, a human-supervised face-recognition workflow, student
self-service attendance, announcements, audit logs, and bounded CSV/PDF
reports.

The production stack is the v2 implementation:

```text
Browser
  -> Nginx frontend (React SPA, /api and /health reverse proxy)
      -> FastAPI backend_v2
          -> PostgreSQL 16
          -> private biometric volume (optional recognition enrollment)
```

The historical `backend/` Flask/MongoDB code remains in the repository only as
migration history. It is not built, started, or connected by the production
Docker Compose topology. The current `frontend/` is Vite + strict TypeScript;
the retired Create React App implementation is not a production entrypoint.

## Delivered MVP capabilities

- Admin: classrooms, subjects, teacher/student profiles, classroom membership,
  exact teacher assignments, timetable, announcements, bounded CSV/XLSX
  imports, biometric enrollment administration, audit logs, and reports.
- Teacher: assigned academic scope, manual attendance, recognition attendance,
  announcements, and classroom/subject reports and exports.
- Student: own profile, own attendance summary/detail and filters, timetable
  visibility through scoped academic APIs, and announcements.
- Reports: bounded attendance detail, defaulters including zero-record active
  students, deterministic leaderboard, formula-safe CSV, and in-memory PDF.
- Security: Argon2id passwords, short-lived JWT access tokens, rotating opaque
  refresh sessions in an HttpOnly cookie, database-derived roles, exact
  object-level attendance authorization, login throttling, explicit CORS and
  trusted-host allow-lists, sanitized error responses, and structured logs.

API contracts are summarized in [API_DOCS.md](API_DOCS.md). FastAPI also
generates OpenAPI from the implemented schemas at `/docs` and `/openapi.json`
when the backend is reached directly on a trusted internal network.

## Face recognition: scope and limitations

The server implements YuNet detection, landmark alignment, dlib 128-dimensional
embeddings, candidate-scoped cosine matching, enrollment processing, and the
recognition-attendance decision workflow. A clear `FOUND` decision writes
attendance only through the existing attendance service. `UNKNOWN` and
`AMBIGUOUS` never write attendance without explicit teacher confirmation from
the authorized classroom roster.

Important limits:

- Model weights are not redistributed in this repository or release ZIP. The
  deployer must independently obtain the reviewed YuNet and dlib model files,
  mount them read-only, and preferably configure their SHA-256 values.
- `FACE_MATCH_THRESHOLD=0.82` is a provisional structural default derived from
  dlib distance guidance. It is not classroom-calibrated accuracy, and this
  project makes no accuracy claim.
- The MVP does not implement liveness/anti-spoofing or automated consent and
  retention workflows. Human supervision remains mandatory.
- A deployment must complete jurisdiction-specific legal/privacy review before
  collecting student biometric data. See
  [docs/BIOMETRIC_DATA_POLICY.md](docs/BIOMETRIC_DATA_POLICY.md).

## Production deployment with Docker Compose

Prerequisites: Docker Engine/Desktop with Compose v2 and an HTTPS ingress or
load balancer for the public hostname.

1. Copy `.env.example` to `.env`.
2. Replace every `CHANGE_ME` and `replace-me` value. Generate a unique
   `SECRET_KEY` of at least 32 random characters and a unique database password.
3. Set `CORS_ALLOWED_ORIGINS` to the exact public HTTPS origin and
   `TRUSTED_HOSTS` to the public host name plus the documented probe hosts.
4. Validate, build, migrate, and start:

```bash
docker compose config --quiet
docker compose build
docker compose up -d postgres
docker compose run --rm migrate
docker compose up -d
docker compose ps
```

The default stack starts only PostgreSQL, the one-shot Alembic migration gate,
`backend_v2`, and the frontend Nginx container. PostgreSQL and the backend have
no public host port. The frontend is published on
`${FRONTEND_BIND_ADDRESS:-0.0.0.0}:${FRONTEND_HOST_PORT:-8080}` and proxies
`/api/*` and `/health/*` to the backend.

Production cookies are `Secure`, so browser authentication requires HTTPS.
The bundled Nginx container serves HTTP for an upstream TLS terminator; do not
expose it as a public production endpoint without TLS.

Verify the running topology:

```bash
curl -fsS http://127.0.0.1:8080/
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
docker compose exec backend_v2 alembic current
```

Create the first admin after migrations:

```bash
docker compose exec backend_v2 python -m scripts.bootstrap_admin
```

The command prompts for the email and password without echoing the password.
No self-registration endpoint exists.

### Migration policy

`migrate` runs `alembic upgrade head` as a one-shot service. Backend startup is
gated on its successful completion, and database downgrade is never automated.
For each release, back up PostgreSQL, review the Alembic history, run the
one-shot migration, confirm `alembic current`, then start/restart the app.

Schema migrations cover PostgreSQL only. Importing historical MongoDB data is a
separate, deployment-specific transform and validation exercise; no production
Compose service connects to MongoDB or performs an implicit dual write.

### Persistence and restart behavior

`shikshasathi_v2_postgres_data` persists PostgreSQL data and
`shikshasathi_v2_biometric_data` persists private enrollment images. Routine
source archives and general code exports exclude biometric data. Back up these
stores deliberately and separately according to local policy.

## Local development

Backend (Python 3.12+ and a reachable PostgreSQL database):

```bash
cd backend_v2
python -m venv .venv
# Windows: .venv\Scripts\activate
# POSIX:   source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Frontend (Node.js 22 recommended):

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

For separate local servers, set `VITE_API_URL=http://localhost:8000/api/v1`
and include `http://localhost:3000` in backend CORS. The default production
frontend build uses same-origin `/api/v1`.

## Required configuration

The root `.env.example` is the production Compose template.
`backend_v2/.env.example` is the standalone backend development template, and
`frontend/.env.example` is public build-time frontend configuration.

The backend fails startup when required database/secret values are missing or
invalid. In production it also rejects debug mode, wildcard/empty CORS,
wildcard/empty trusted hosts, and an insecure refresh cookie. Never put a real
credential, token, model file, biometric image, or `.env` in source or a release
archive.

Proxy trust is intentionally tied to the shipped topology: Compose sets
`FORWARDED_ALLOW_IPS=*` only because `backend_v2` is not host-published and the
frontend reverse proxy is the sole ingress on the private Compose network. If
the backend is exposed or another proxy path is added, restrict this value to
the exact trusted proxy addresses.

## Verification commands

Backend, against an isolated PostgreSQL test database:

```bash
docker compose --profile test up -d postgres_test
docker compose --profile test run --rm backend_v2_test
```

The release/CI quality policy runs:

```bash
cd backend_v2
alembic upgrade head
pytest
ruff format --check app alembic scripts
ruff check app alembic scripts
mypy app --exclude 'app/tests'
python -m compileall -q app alembic scripts

cd ../frontend
npm ci
npm run typecheck
npm run lint
npm test -- --run
npm run build
npm audit
```

CI is defined in `.github/workflows/ci.yml` for pull requests and pushes to
`main`. It runs PostgreSQL migrations and the full backend suite, frontend
quality/build/audit gates, and both production image builds. It contains only
test placeholders—no repository or deployment secret.

## Repository map

```text
backend_v2/             FastAPI application, Alembic migrations, tests, image
frontend/               React 19 + TypeScript + Vite app and Nginx image
docs/                   architecture, policy, ADRs, phase handovers
.github/workflows/      continuous integration
docker-compose.yml      production stack plus isolated test profile
backend/                retired legacy Flask/Mongo source (not production)
API_DOCS.md             implemented v2 API summary
```

Phase-specific decisions and verification evidence are preserved under
`docs/HANDOVER_PHASE_*.md`. Phase 9 completes the Deployable MVP; Milestone 2
(accessibility/UX polish, stronger observability, deeper performance and
biometric lifecycle work) is separate and has not started.
