# ADR 0003: Use React + TypeScript + Vite for the frontend

## Status
Accepted

## Context
The legacy frontend is React 19 bootstrapped with Create React App (`react-scripts`), in plain JavaScript. Two concrete problems observed during the audit are directly attributable to the lack of types and to CRA specifically:
- **Critical finding C3** (`docs/AUDIT.md` §3.2): `src/App.jsx` imports `StudentRoutes` from `./routes/StudentRoutes`, a file that is completely empty (no export at all). In plain JS with no build-time type checking, this was never caught — it only fails at runtime, when a student actually logs in. A typed import of a non-existent export would be a compile-time error under TypeScript.
- `README.md` already states the frontend uses **Vite** (`docs/AUDIT.md` §4.1) — the actual code uses CRA. `react-scripts` is also effectively unmaintained upstream, which is itself a reason to move off it independent of the README mismatch.

## Decision
Rebuild the frontend with React + TypeScript, using Vite as the build tool.

## Alternatives considered
- **Keep CRA, add TypeScript to it.** Rejected: CRA's own maintenance status is a separate problem from typing, and since a full frontend rewrite is already in scope (per the migration map's "Rewrite" decision for the application shell and routing, driven by C3), there's no reason to keep the older build tool.
- **Next.js.** Considered for its stronger conventions and built-in routing; rejected for this project because the backend is a separate FastAPI service (`docs/adr/0001-use-fastapi.md`) and there's no current need for server-side rendering or Next-specific data-fetching patterns — a plain Vite SPA matches the existing architecture (separate API + SPA) most directly.
- **Remix.** Same reasoning as Next.js — not needed given the separate-backend architecture.

## Consequences
- Every route and component gets a compile-time-checked import graph — the specific failure mode behind C3 becomes structurally impossible to ship silently.
- Tailwind CSS config moves from CRA's build pipeline to Vite's (`docs/LEGACY_MIGRATION_MAP.md` — Tailwind is a "Reuse" of the styling approach, not the build config).
- Test tooling moves from whatever CRA would have used to Vitest + React Testing Library, matching the target architecture (`docs/ARCHITECTURE.md` §11). This is a new addition either way — the legacy app has no frontend tests today.
- `REACT_APP_API_URL` (CRA's env-var convention) is renamed to Vite's `VITE_`-prefixed convention during the rebuild; noted so it isn't missed as a "just works the same" assumption.
