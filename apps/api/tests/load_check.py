"""Load check for the pilot (spec M4, AC5). Not part of `pnpm check`: run it before go-live.

Builds the e2e world in the throwaway `dl360_e2e` database, starts the API on port 8363
(one process, like Render), signs a parent in, then measures:

1. 200 parents opening the portal at once (results + fees).
2. 50 report-card PDFs requested at once (AC5: each < 5 s, all < 2 min), while other
   parents keep loading pages (they must not stall behind the PDFs).

    cd apps/api && uv run python -m tests.load_check

Needs Docker Postgres + Redis (pnpm dev's ones are fine; it uses its own database and
Redis db 2). Numbers from a laptop are an upper bound for Render's free tier, which has
a fraction of a CPU.
"""

import asyncio
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

PORT = 8363
API_DIR = Path(__file__).resolve().parents[1]
HOST = "e2e.digitallearning360.localhost"
PROXY_KEY = "load-proxy-key"


def _env(outbox: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DL360_ENV": "local",
        "DL360_DATABASE_URL": "postgresql+asyncpg://dl360_app:dl360_app@localhost:5436/dl360_e2e",
        "DL360_MIGRATION_DATABASE_URL": "postgresql+asyncpg://dl360:dl360@localhost:5436/dl360_e2e",
        "DL360_REDIS_URL": "redis://localhost:6380/2",
        "DL360_PROXY_KEY": PROXY_KEY,
        "DL360_BASE_DOMAIN": "digitallearning360.localhost",
        "DL360_DEFAULT_SCHOOL_SLUG": "",
        "DL360_EMAIL_OUTBOX_FILE": str(outbox),
        "DL360_PAYSTACK_SECRET_KEY": "",
    }


def _summary(name: str, latencies: list[float], wall: float) -> str:
    ordered = sorted(latencies)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    return (
        f"{name:<44} n={len(ordered):<4} p50={statistics.median(ordered):6.2f}s "
        f"p95={p95:6.2f}s max={ordered[-1]:6.2f}s wall={wall:6.2f}s"
    )


async def _timed(coro_factory) -> float:  # type: ignore[no-untyped-def]
    t0 = time.perf_counter()
    res = await coro_factory()
    res.raise_for_status()
    return time.perf_counter() - t0


async def run(outbox: Path, world: dict[str, object]) -> list[str]:
    limits = httpx.Limits(max_connections=300, max_keepalive_connections=300)
    headers = {"x-dl360-proxy-key": PROXY_KEY, "x-dl360-host": HOST}
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{PORT}", headers=headers, limits=limits, timeout=180
    ) as c:
        email = world["parent"]["email"]  # type: ignore[index]
        (await c.post("/api/auth/parent/code", json={"email": email})).raise_for_status()
        code = re.findall(r"\b(\d{6})\b", outbox.read_text(encoding="utf-8"))[-1]  # noqa: ASYNC240
        (
            await c.post("/api/auth/parent/verify", json={"email": email, "code": code})
        ).raise_for_status()
        snap = (await c.get("/api/portal/results")).json()[0]["results"][0]["snapshot_id"]
        await c.get(f"/api/reports/{snap}.pdf")  # warm up fonts and caches

        lines = []
        t0 = time.perf_counter()
        portal = await asyncio.gather(
            *[_timed(lambda: c.get("/api/portal/results")) for _ in range(200)],
            *[_timed(lambda: c.get("/api/fees/mine")) for _ in range(200)],
        )
        lines.append(
            _summary(
                "200 parents: results + fees (400 requests)", list(portal), time.perf_counter() - t0
            )
        )

        t0 = time.perf_counter()
        pdfs_task = asyncio.gather(
            *[_timed(lambda: c.get(f"/api/reports/{snap}.pdf")) for _ in range(50)]
        )
        await asyncio.sleep(0.2)  # PDFs are rendering now
        during = await asyncio.gather(
            *[_timed(lambda: c.get("/api/portal/results")) for _ in range(20)]
        )
        pdfs = await pdfs_task
        lines.append(
            _summary("50 report-card PDFs at once (AC5)", list(pdfs), time.perf_counter() - t0)
        )
        lines.append(_summary("  portal pages during the PDF burst", list(during), max(during)))
        return lines


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        outbox, world_file = Path(tmp) / "outbox.jsonl", Path(tmp) / "world.json"
        env = _env(outbox)
        # Fixed commands, no user input.
        subprocess.run([sys.executable, "-m", "tests.e2e_world", str(world_file)], cwd=API_DIR, env=env,  # noqa: S603
                       check=True, stdout=subprocess.DEVNULL)  # fmt: skip
        world = json.loads(world_file.read_text(encoding="utf-8"))
        server = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
            cwd=API_DIR, env=env,
        )  # fmt: skip
        try:
            for _ in range(60):
                try:
                    if httpx.get(f"http://127.0.0.1:{PORT}/healthz").status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.5)
            lines = asyncio.run(run(outbox, world))
        finally:
            server.terminate()
            server.wait(timeout=20)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
