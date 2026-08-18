# ADR 0004: Use a modular monolith, not microservices

## Status
Accepted

## Context
ShikshaSathi is, and will remain at both Milestone 1 and Milestone 2 (`docs/IMPLEMENTATION_PLAN.md`), a single-institution-scale attendance and academic-management system. The legacy codebase is already a single Flask service with a reasonably sensible internal split (`api/v1/`, `services/`, `models/`, `ml/`), just not consistently followed — two service files went empty and dead without breaking anything because nothing enforced that a route's imports actually match a populated module (`docs/AUDIT.md`, Legacy Migration Map rows for Timetable/Announcements). There is one real, currently-broken cross-cutting concern (face recognition — `docs/AUDIT.md` §2.13) that is naturally a distinct module, not a distinct service.

## Decision
Keep the backend as a single deployable FastAPI service, internally organized into clearly bounded modules (`docs/ARCHITECTURE.md` §2), rather than splitting into separate deployable microservices.

## Alternatives considered
- **Microservices** (e.g., a separate face-recognition service, a separate reporting service). Rejected for this project's scale: it would add deployment/operations complexity (service discovery, inter-service auth, network calls replacing function calls) with no corresponding benefit at a single-institution scale, and would work against the rebuild brief's explicit constraint to avoid over-engineering with microservices or Kubernetes.
- **Serverless functions per endpoint.** Rejected: doesn't fit the stateful, session/JWT-heavy access pattern well, and would fragment the object-level-authorization logic (`docs/ARCHITECTURE.md` §5) that specifically needs to be applied consistently — the opposite of what Critical finding C4 calls for.

## Consequences
- One deployment unit for the backend, one for the frontend, simplifying `docker-compose.yml` (`docs/ARCHITECTURE.md` §12).
- Module boundaries (`modules/<name>/` with router/service/repository/schemas/models co-located) are enforced by convention and code review, not by network/process boundaries — this requires discipline that the legacy app didn't fully maintain (hence the dead service files). Recommend a lint rule or periodic audit (candidate for Phase 9 CI) checking for unreferenced modules.
- If a specific module (most plausibly face recognition, given its CPU/GPU profile) later needs independent scaling, it can be split out at that point — this decision does not preclude that, it just doesn't do it preemptively.
