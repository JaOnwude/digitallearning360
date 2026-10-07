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
docker compose -f infra/docker-compose.yml up -d   # once per PC restart
pnpm dev        # API (yellow) + website (cyan) together; Ctrl+C stops both
```
Then open http://progress.digitallearning360.localhost:3360 (API docs: http://localhost:8360/docs).

## Checks
```bash
pnpm check   # lint, types, tests, generated-client drift; also runs automatically on git push
```
GitHub Actions CI is currently manual-only (see `.github/workflows/ci.yml`).
