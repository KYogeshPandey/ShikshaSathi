# ADR 0001: Use FastAPI for the backend

## Status
Accepted

## Context
The legacy backend is Flask 3.0 with manual JSON parsing, hand-rolled validation via a small set of Pydantic models used inconsistently, and no auto-generated API documentation (`docs/API_DOCS.md` is hand-maintained and not verified against the live server — `docs/AUDIT.md` §4.2). Error handling is ad hoc per-route (`docs/AUDIT.md` §2.7), and there is no dependency-injection mechanism, which contributed to authorization logic being duplicated across two inconsistent decorators (`docs/AUDIT.md` §2.4).

## Decision
Rebuild the backend on FastAPI.

## Alternatives considered
- **Stay on Flask, harden it in place.** Rejected as the primary path: Flask's ecosystem for typed request/response validation, dependency injection, and auto-generated OpenAPI docs is weaker than FastAPI's, and the legacy app's problems (inconsistent auth decorators, no schema enforcement on every route, stale hand-written docs) are exactly the class of problem FastAPI's design pushes against structurally rather than by convention.
- **Django / Django REST Framework.** Rejected as heavier than this project needs — DRF brings a lot of batteries (admin site, ORM conventions) that don't map cleanly onto the modular-monolith shape already chosen (`docs/adr/0004-use-modular-monolith.md`), and the team's existing familiarity is with Flask-style routing, which FastAPI is closer to.
- **Node/Express or NestJS**, unifying the stack around TypeScript end-to-end. Rejected for this rebuild: Python is kept on the backend to preserve the face-recognition path (OpenCV/MTCNN-class libraries are Python-first — see `docs/adr/0005-face-recognition-provider-pending.md`), avoiding an awkward split where the face-recognition module would need its own separate Python service.

## Consequences
- Pydantic v2 becomes the single source of truth for request/response shapes, replacing the legacy app's partial/inconsistent use of `schemas/`.
- OpenAPI docs are generated from code, closing the README/API_DOCS drift found in the audit (`docs/AUDIT.md` §4.1–§4.2).
- Async-first framework — repository/service code should be written async-aware from the start rather than retrofitted.
- Team needs to learn FastAPI's dependency-injection style for auth/ownership checks (`docs/ARCHITECTURE.md` §4–§5); this is new compared to the legacy decorator pattern, but is the direct structural fix for Critical finding C4 (missing object-level authorization).
