# DigitalLearning360

Multi-tenant school management SaaS for Nigerian schools (creche → SS3).
**The spec is the source of truth:** `docs/specs/project-school-management-system.md`.
Requirements are numbered (R1…, AC1…); reference them in commits and PRs.
Pilot school material (report card template, logo) is in `docs/pilot-school/`.

## Backend structure (feature-based)
Each feature folder in `apps/api/app/` owns its `models.py`, `schemas.py`, `service.py`,
`router.py` (e.g. `tenancy/`, `auth/`, `academics/`, `students/`, `staff/`, `audit/`).
Register new models in `app/db/registry.py` and routers in `app/main.py`. Tests mirror
features in `apps/api/tests/`. Every school-scoped endpoint uses `TenantDB` and an auth
dependency (`SchoolAdmin`, `require_roles(...)`), loads rows with `get_or_404`, and gets a
case in `tests/tenancy/test_isolation_sweep.py` (the test fails if a route is missing).

## Layout
- `apps/api`: FastAPI + SQLAlchemy 2.0 (async) + Alembic. Python 3.13, managed by **uv**.
- `apps/web`: Next.js 16 (App Router) + Tailwind v4 + shadcn/ui + TanStack Query.
  Next 16 differs from older versions: read `apps/web/node_modules/next/dist/docs/`
  before using a Next API you're unsure of (e.g. `proxy.ts` replaced `middleware.ts`).
- `packages/api-client`: **generated** TS client (Orval: fetch + TanStack Query hooks + Zod).
  Never hand-edit `src/gen/**`. Regenerate with `pnpm gen:client` after any API change.
- `infra/docker-compose.yml`: local Postgres (port 5436) and Redis (port 6380).

## Commands
```bash
docker compose -f infra/docker-compose.yml up -d     # start Postgres + Redis
pnpm dev                                             # API + web together (or dev:api / dev:web)
pnpm gen:client                                      # API changed → regenerate client
pnpm check                                           # everything CI would run (also runs on git push)
cd apps/api && uv run alembic revision --autogenerate -m "..." && uv run alembic upgrade head
```
Ports 3000/8000/5433 are used by other projects on this machine. Ours are 3360/8360/5436/6380.

## Local hostnames
Schools resolve by subdomain: `http://{slug}.digitallearning360.localhost:3360`.
The API is at `http://api.digitallearning360.localhost:8360`, on the same site so
session cookies work. Browsers resolve `*.localhost` to 127.0.0.1 with no hosts-file edits.

## Non-negotiable rules
- **Tenancy:** every school-owned table has `school_id` and an RLS policy (R1).
  Never query tenant data outside the request's tenant transaction. Add a
  cross-school isolation test for every new endpoint (AC1).
- **Money:** integer **kobo** only. Balances are derived from `ledger_entries`.
  Apply payments under `SELECT … FOR UPDATE` on the invoice. Webhooks are idempotent (R21–R22).
- **Results:** published results are immutable except via an audit-logged override (R15).
- **Config over code:** level names, assessment components, grading bands,
  traits, comment slots and report layouts are per-**section** data, never hard-coded (R9–R17).
- **Auth:** httpOnly cookie sessions only. No tokens in localStorage/sessionStorage (R7).
- **Design:** use tokens from `apps/web/src/app/globals.css` (`brand`, `brand-ink`,
  `success`, `warning`, motion vars). No raw hex colors in components.
  Respect `prefers-reduced-motion`. Parent pages: mobile-first, at most 170 KB JS per route.
- API schemas (Pydantic) are separate from DB models (SQLAlchemy). No SQLModel.
- Tests hit real Postgres via testcontainers. Don't mock the database.

## Workflow
- Big changes: plan mode first, then implement in small slices with tests.
- Before saying a task is done: `pnpm check` passes and the page is checked in the browser.
- **GitHub Actions is disabled** (account billing lock), so CI is manual-only. The
  pre-push hook (`.githooks/pre-push`, enabled by `pnpm install`) is the safety net. Never bypass it.
- Git identity on this machine is JaOnwude's (shared project account; intentional).
