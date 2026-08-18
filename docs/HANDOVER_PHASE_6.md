# Phase 6 final handover

## Closure status

**Phase 6 is complete as of 2026-08-16.** The legacy Create React App shell has
been replaced by a working Vite + React + TypeScript application foundation.
Phase 7 was not started. No Git operation was performed.

The input workspace was created from the authoritative
`ShikshaSathi-phase-5-complete.zip` artifact with recorded SHA-256
`3ba25247aefd69487561f75e4f501ba98a7dba094dd358fda1902073b28fecf8`.
Phase 5 backend behavior remained locked and unchanged.

## Frontend architecture and tooling

The Phase 6 frontend uses:

- React 19.2.8 and React DOM 19.2.8;
- TypeScript 5.9.3 in strict mode;
- Vite 8.2.1 with `@vitejs/plugin-react` 6.0.5;
- React Router DOM 7.18.2;
- TanStack React Query 5.101.4;
- React Hook Form 7.85.0, Hook Form resolvers 5.9.0, and Zod 3.25.76;
- Vitest 4.1.10, React Testing Library 16.3.2, jest-dom 7.0.1, user-event
  14.6.4, and jsdom 28.1.0;
- ESLint 9.39.5 with TypeScript ESLint 8.55.0 and React hooks/refresh rules.

Vite runs on port 3000 in development so it matches the existing backend
example CORS allow-list. Styling is a small responsive CSS system rather than
retaining the legacy Tailwind/CRA pipeline. This keeps the Phase 6 shell
self-contained while preserving the existing project's calm card/sidebar
visual direction. No fake statistics, full CRUD UI, attendance workflow,
camera workflow, report, or analytics screen was migrated.

The final source layout is:

```text
frontend/
  src/
    api/          typed client, auth endpoint facade, error types, 401 tests
    app/          root route tree, providers, application tests
    auth/         narrow context/provider and in-memory token session
    components/   shared loading UI
    layouts/      common role shell plus admin/teacher/student wrappers
    lib/          QueryClient configuration
    pages/        login, status pages, role dashboards/placeholders
    routes/       typed route config and auth/role guards
    test/         test setup and typed user fixtures
    types/        auth/user/API DTOs
```

## API client design

`src/api/client.ts` is the only HTTP transport. It centralizes:

- the normalized `VITE_API_URL` base (with a same-origin `/api/v1` fallback);
- JSON encoding/decoding and `Accept`/`Content-Type` headers;
- `credentials: "include"` for the backend's cookie contract;
- Bearer access-token attachment;
- the FastAPI error envelope (`error.code`, safe message/details,
  `request_id`) as a typed `ApiError`;
- network and malformed-response failures without exposing raw backend text;
- protected-request 401 refresh and one controlled retry.

No component contains a raw fetch/axios base URL. `.env.example` contains only
the public development API root and no secret.

## Auth and token-storage decision

The access token is stored only in `MemoryAuthSession`; it is never persisted
to local storage, session storage, a URL, or a cookie created by JavaScript.
The current user is the single `auth/current-user` TanStack Query value exposed
through the narrow Auth context. Components do not hold duplicate user/token
copies.

The backend-issued rotating refresh token stays in its HttpOnly, SameSite
cookie. JavaScript neither reads nor mirrors it. On application bootstrap the
auth provider calls `/auth/refresh` with credentials, stores the new access
token in memory, then calls the protected `/auth/me` endpoint. A failed restore
resolves to unauthenticated state; it never invents a second session mechanism.

Login posts `{email, password}` to the real `/auth/login` contract, stores the
returned access token in memory, obtains the authoritative current user from
`/auth/me`, then redirects by `user.role`. Logout calls `/auth/logout`, clears
frontend-controlled state in a `finally` path, removes non-auth server queries,
and returns to login. Passwords and tokens are never logged.

## Centralized 401 behavior

When an authenticated API request returns 401:

1. the client starts or joins one shared in-flight `/auth/refresh` request;
2. successful refresh replaces the in-memory access token;
3. the original request is retried exactly once with the new Bearer token;
4. refresh failure invalidates the memory session and notifies the Auth
   provider, which clears server-state queries and exposes unauthenticated
   state;
5. route guards send the user to `/login`.

The retry flag prevents loops. Login uses no refresh retry, the refresh request
cannot recursively refresh itself, and 403 authorization failures are surfaced
without refresh. Tests cover success, failure/logout notification, concurrent
refresh de-duplication, Authorization header replacement, cookie credentials,
and 403 non-refresh behavior.

## TanStack Query setup

One root `QueryClient` is constructed in `src/lib/queryClient.ts` and provided
once by `AppProviders`. Queries have a 30-second default stale time, do not
refetch on window focus, and retry at most once. `ApiError` statuses 401, 403,
and 422 are never aggressively retried; mutations have no automatic retry.
Auth bootstrap/current-user state uses the `auth/current-user` query. Future
Phase 7 server data should add typed queries rather than expanding Auth
Context.

## Role routing and student regression closure

Public routes are `/login`, `/unauthorized`, and not-found handling. The root
redirects an authenticated user to their own role home. Protected route shells
are `/admin/*`, `/teacher/*`, and `/student/*`.

`AuthenticatedRoute` rejects missing sessions. `RoleRoute` separately checks
the authenticated database-derived role before rendering its outlet. Wrong
roles go to an explicit unauthorized page; hidden links are not the guard.
Each role has a real non-empty layout, identity display, accessible navigation,
logout, overview, clearly labelled Phase 7 placeholder, and nested wildcard.

The regression test renders `/student/a-future-page` as an authenticated
student and asserts the Student shell, navigation, identity, and safe wildcard
page. Separate checks prove a teacher cannot render the student shell. Typed
imports and strict typechecking make the former missing-export failure
structurally visible at build time.

## Verification results

Environment: Node 22.12.0 and npm 10.9.0.

- `npm run typecheck` — passed, zero errors. The exact script is
  `tsc --noEmit`, and the root `tsconfig.json` includes all `src` files and
  `vite.config.ts`.
- `npm run build` — passed. Vite transformed 109 modules and emitted the
  production `dist` bundle successfully.
- `npm test -- --run` — passed: **2 test files, 18 tests**.
- `npm run lint` — passed: zero errors and zero warnings.
- `npm audit` — passed: zero vulnerabilities after a compatible transitive
  `fast-uri` security update.

The 18 unit/component tests cover root render, bootstrap loading, form
validation, successful role redirect, unauthenticated redirect, logout, all
three allowed role shells, wrong-role denial for all roles, student wildcard
render, explicit student denial to another role, refresh success/retry,
concurrent refresh de-duplication, refresh failure auth invalidation, and 403
non-refresh behavior. The network boundary is mocked; PostgreSQL is not
required.

Source inspection found no explicit `any`, `@ts-ignore`, broad
`eslint-disable`, `localStorage`/`sessionStorage`, CRA/react-scripts, axios,
console logging of auth data, empty TS/TSX modules, legacy JS/JSX, or scattered
hard-coded API origins.

## Files added, modified, and deleted

Added:

- `docs/HANDOVER_PHASE_6.md`
- `frontend/.env.example`
- `frontend/eslint.config.js`
- `frontend/index.html`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- every final file under `frontend/src/`: `api/auth.ts`, `api/client.ts`,
  `api/client.test.ts`, `api/types.ts`, `app/App.tsx`, `app/App.test.tsx`,
  `app/AppProviders.tsx`, `auth/authContext.ts`, `auth/AuthProvider.tsx`,
  `auth/session.ts`, `components/LoadingScreen.tsx`, `layouts/AdminLayout.tsx`,
  `layouts/RoleLayout.tsx`, `layouts/StudentLayout.tsx`,
  `layouts/TeacherLayout.tsx`, `lib/queryClient.ts`, `main.tsx`,
  `pages/AdminDashboard.tsx`, `pages/LoginPage.tsx`, `pages/NotFoundPage.tsx`,
  `pages/PhaseSevenPlaceholder.tsx`, `pages/RoleDashboard.tsx`,
  `pages/RoleNotFoundPage.tsx`, `pages/StudentDashboard.tsx`,
  `pages/TeacherDashboard.tsx`, `pages/UnauthorizedPage.tsx`,
  `routes/AuthenticatedRoute.tsx`, `routes/config.ts`,
  `routes/HomeRedirect.tsx`, `routes/RoleRoute.tsx`, `styles.css`,
  `test/setup.ts`, `test/testUsers.ts`, `types/auth.ts`, and `vite-env.d.ts`.

Modified:

- `docs/IMPLEMENTATION_PLAN.md`
- `docs/PROGRESS.md`
- `frontend/.gitignore`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/README.md`

Deleted:

- `frontend/postcss.config.js`
- `frontend/tailwind.config.js`
- `frontend/public/index.html`
- `frontend/public/manifest.json`
- `frontend/public/robots.txt`
- `frontend/src/App.jsx`
- `frontend/src/index.css`
- `frontend/src/index.js`
- `frontend/src/reportWebVitals.js`
- `frontend/src/api/api.js`
- `frontend/src/components/ExportPDFButton.jsx`
- `frontend/src/components/Teacher/DefaulterListTable.jsx`
- `frontend/src/components/Teacher/TeacherStatsCards.jsx`
- `frontend/src/components/charts/AttendanceBarChart.jsx`
- `frontend/src/components/charts/AttendancePieChart.jsx`
- `frontend/src/components/common/Card.jsx`
- `frontend/src/components/common/Navbar.jsx`
- `frontend/src/components/common/Sidebar.jsx`
- `frontend/src/components/common/loader.jsx`
- `frontend/src/components/forms/BulkImportForm.jsx`
- `frontend/src/components/forms/ClassForm.jsx`
- `frontend/src/components/notices/CreateNoticeModal.jsx`
- `frontend/src/components/notices/NoticeBoard.jsx`
- `frontend/src/components/tables/AttendanceDetailTable.jsx`
- `frontend/src/components/tables/AttendanceTable.jsx`
- `frontend/src/components/tables/ClassroomsTable.jsx`
- `frontend/src/components/tables/StudentsTable.jsx`
- `frontend/src/components/tables/TeachersTable.jsx`
- `frontend/src/components/timetable/TimetableGrid.jsx`
- `frontend/src/context/AuthContext.jsx`
- `frontend/src/hooks/useAttendanceStats.js`
- `frontend/src/hooks/useAuth.js`
- `frontend/src/layout/AdminLayout.jsx`
- `frontend/src/layout/DashboardLayout.jsx`
- `frontend/src/layout/StudentLayout.jsx`
- `frontend/src/layout/TeacherLayout.jsx`
- `frontend/src/pages/Admin/AdminDashboard.jsx`
- `frontend/src/pages/Admin/AttendanceDetailPage.jsx`
- `frontend/src/pages/Admin/AuditLogPage.jsx`
- `frontend/src/pages/Admin/BulkImportPage.jsx`
- `frontend/src/pages/Admin/ClassroomsPage.jsx`
- `frontend/src/pages/Admin/StudentsPage.jsx`
- `frontend/src/pages/Admin/SubjectsPage.jsx`
- `frontend/src/pages/Admin/TeachersPage.jsx`
- `frontend/src/pages/Auth/LoginPage.jsx`
- `frontend/src/pages/Student/StudentDashboard.jsx`
- `frontend/src/pages/Teacher/AnnouncementsPage.jsx`
- `frontend/src/pages/Teacher/AttendancePage.jsx`
- `frontend/src/pages/Teacher/ClassDetailsPage.jsx`
- `frontend/src/pages/Teacher/MyClassesPage.jsx`
- `frontend/src/pages/Teacher/TeacherDashboard.jsx`
- `frontend/src/pages/Teacher/TeacherReportsPage.jsx`
- `frontend/src/pages/Teacher/TimetablePage.jsx`
- `frontend/src/routes/AdminRoutes.jsx`
- `frontend/src/routes/ProtectedRoute.jsx`
- `frontend/src/routes/StudentRoutes.jsx`
- `frontend/src/routes/TeacherRoutes.jsx`
- `frontend/src/styles/index.css`
- `frontend/src/styles/tailwind.css`
- `frontend/src/utils/constants.js`
- `frontend/src/utils/formatters.js`
- `frontend/src/utils/storage.js`

Generated `node_modules`, `dist`, and TypeScript build-info/cache artifacts are
not release files and are excluded from the final archive.

## Known limitations and exact Phase 7 starting point

- Phase 6 provides role shells, not full admin CRUD, teacher workflows,
  student attendance/dashboard features, recognition camera UI, or analytics.
- Tests use a mocked browser network boundary. A live browser-to-FastAPI smoke
  test and end-to-end test suite remain future integration work.
- Access tokens deliberately disappear on reload; bootstrap obtains a new one
  from the HttpOnly refresh cookie. If logout cannot reach the backend, the
  frontend still clears memory, but only the backend can revoke/clear its
  HttpOnly refresh session.
- The app assumes deployment routes SPA fallbacks to `index.html` for direct
  navigation to role paths.

Phase 7 should begin inside the existing guarded layouts by adding typed
domain DTOs and TanStack Query hooks for the already-authoritative Phase 3-5
APIs, followed by scoped admin, teacher, and student feature pages. It must
reuse `ApiClient`, `AuthProvider`, the memory-only token decision, and the role
guards rather than adding storage, fetch instances, or another auth context.

**Phase 7 was not started.**
