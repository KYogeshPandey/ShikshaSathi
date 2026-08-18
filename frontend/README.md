# ShikshaSathi frontend

React 19 + strict TypeScript + Vite frontend for Admin, Teacher, and Student
workflows. Server state uses TanStack Query, forms use React Hook Form + Zod,
and all network traffic uses the typed client in `src/api/client.ts`.

The access token remains in memory. The backend-issued rotating refresh token
is an HttpOnly cookie and is never read by JavaScript. The client performs one
shared refresh and one retry after a protected 401; it does not refresh on 403.

## Local development

```bash
npm ci
cp .env.example .env.local
npm run dev
```

For a backend running separately on port 8000, set
`VITE_API_URL=http://localhost:8000/api/v1` and allow the Vite origin in backend
CORS. Production builds use same-origin `/api/v1` through Nginx.

## Quality gates

```bash
npm run typecheck
npm run lint
npm test -- --run
npm run build
npm audit
```

## Production image

`frontend/Dockerfile` runs `npm ci`, typecheck, and the Vite production build in
Node 22, then copies only `dist/` into an unprivileged Nginx 1.28 runtime.
`nginx.conf` provides SPA fallback, immutable asset caching, no-cache HTML,
security headers, bounded upload forwarding, and `/api`/`/health` proxying to
`backend_v2`. No token or secret is a frontend build argument.
