# Production image for the API (and, later, the arq worker).
# --timeout-graceful-shutdown: live-update (SSE) streams never close by themselves, so without
# it a deploy waits on them; browsers reconnect on their own.
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN useradd --create-home appuser
USER appuser
ENV PATH="/app/.venv/bin:$PATH" DL360_ENV=production
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 10"]
