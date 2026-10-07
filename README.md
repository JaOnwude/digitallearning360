# DigitalLearning360

School management for Nigerian schools: results and report cards, fees and
payments (Paystack and bank transfer), attendance, timetables and CBT, from
creche to SS3. Built for many schools; piloting with Progress Junior Secondary
School, Abakaliki.

- Product spec: [docs/specs/project-school-management-system.md](docs/specs/project-school-management-system.md)
- Contributor and AI-assistant guide: [CLAUDE.md](CLAUDE.md)

## Prerequisites
Git, Node 24 + pnpm 10, [uv](https://docs.astral.sh/uv/) (installs Python 3.13 for you), Docker.

## First run
```bash
pnpm install
docker compose -f infra/docker-compose.yml up -d
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
cd apps/api && uv sync && uv run alembic upgrade head
```

## Day to day
```bash
cd apps/api && uv run fastapi dev app/main.py --port 8360   # API docs: http://localhost:8360/docs
pnpm dev:web                                                # http://progress.digitallearning360.localhost:3360
```

## Checks
```bash
pnpm check   # lint, types, tests, generated-client drift; also runs automatically on git push
```
GitHub Actions CI is currently manual-only (see `.github/workflows/ci.yml`).
