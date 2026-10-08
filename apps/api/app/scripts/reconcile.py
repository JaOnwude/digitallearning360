"""Re-check pending Paystack payments now, instead of waiting for the 30-minute timer.

cd apps/api && uv run python -m app.scripts.reconcile
"""

import asyncio

from app.core.redis import close_redis
from app.db.session import dispose_engine
from app.fees.reconcile import run_once_locked


async def main() -> None:
    try:
        report = await run_once_locked()
        if report is None:
            print("Skipped: no Paystack key configured, or a reconcile is already running.")
        else:
            print(
                f"Checked {report.checked}: {report.applied} applied, {report.failed} failed, "
                f"{report.still_pending} still in progress."
            )
            for error in report.errors:
                print(f"  error: {error}")
    finally:
        await dispose_engine()
        await close_redis()


if __name__ == "__main__":
    asyncio.run(main())
