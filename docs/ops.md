# Running DigitalLearning360 (ops runbook)

Who this is for: Anthony and Jude, running the pilot for Progress JSS. Deploying
staging the first time: [deploy-staging.md](deploy-staging.md).

## What runs where

| Piece | Where | Notes |
|---|---|---|
| Web app (Next.js) | Vercel | Serves pages; forwards `/api/*` to the API with the proxy key. |
| API (FastAPI) | Render `dl360-api` | One process. Migrations run at each deploy. |
| Database | Neon (Frankfurt) | The API connects as `dl360_app` (row-level security applies). |
| Sessions, rate limits, live updates | Render Key Value (Redis) | Losing it signs everyone out; no data is lost. |

The API **refuses to start** in staging/production if its database role could
bypass row-level security (superuser, BYPASSRLS, or table owner). If a deploy
fails with "can bypass tenant isolation", `DL360_DATABASE_URL` is pointing at the
owner: use the `dl360_app` string (deploy-staging.md step 0).

## Keeping it awake

Render's free plan sleeps after 15 idle minutes. An UptimeRobot monitor on
`<Render URL>/healthz` every 5 minutes keeps it up (one service fits in the free
750 hours a month). `/readyz` also checks the database and Redis: use it for a
second, alerting monitor.

## Background jobs (inside the API process)

Every 30 minutes, one instance at a time (Redis lock):

- **Paystack reconciliation.** Re-checks checkouts still "pending" 10+ minutes
  later, in case both the webhook and the parent's return page were lost, and
  applies them through the same exactly-once path. Checkouts still in progress
  at Paystack are left alone for 24 hours, then marked failed. Run it now:
  `cd apps/api && uv run python -m app.scripts.reconcile` (with the staging env).
  The log line `paystack.reconciled_missed_payment` means it caught one.
- **Retention.** Transfer-receipt images are deleted one year after the bursar
  reviews them (the payment record stays), as the privacy notice promises.

## Backups

Neon keeps its own short restore history (free plan: about a day). On top of
that, take our own copy **every week**, and before any risky change:

```bash
DL360_BACKUP_URL='<Neon OWNER connection string>' scripts/backup/backup.sh
```

It writes `~/dl360-backups/dl360-<time>.dump` plus a `.counts` file (row counts
for checking a restore), keeps the newest 14, and needs only Docker. Keep the
folder off the repo and, ideally, synced to a second place (Google Drive).

Weekly on Windows: Task Scheduler → Create Basic Task → Weekly → Start a
program `C:\Program Files\Git\bin\bash.exe` with arguments
`-lc "DL360_BACKUP_URL='<owner string>' '/c/Users/Dell/Documents/School Management System/scripts/backup/backup.sh'"`.
(Docker Desktop must be running.)

**First staging backup:** check it succeeds. The backup reads every school's
rows, so the owner role must be allowed past row-level security. If it fails
with a "row-level security" error, tell Claude; until it's fixed, Neon's own
restore is the only backup.

## Restore drill (spec AC12)

```bash
scripts/backup/restore-drill.sh                 # newest backup in ~/dl360-backups
scripts/backup/restore-drill.sh path/to/x.dump  # a specific one
```

It restores into a brand-new throwaway Postgres container, then checks that
every table's row count matches the backup, that every school table still has
row-level security on, and that the app role sees nothing without a school.
Nothing else is touched. Do it monthly and after the first staging backup.

| Date | Backup | Result |
|---|---|---|
| 2026-10-08 | local dev database (42 tables, 460 KB) | PASSED in 11 s. A deliberately broken copy (RLS off on `students`) was caught by both checks. |

**Real restore:** restore into a new Neon branch or database the same way
(`pg_restore --no-owner`), create `dl360_app` as in deploy-staging.md step 0,
run the drill's checks, then point `DL360_DATABASE_URL` and
`DL360_MIGRATION_DATABASE_URL` at it and redeploy.

## Capacity (load check, 2026-10-08)

`cd apps/api && uv run python -m tests.load_check` (builds its own database).
One API process on Anthony's laptop:

| Scenario | p50 | p95 | Total |
|---|---|---|---|
| 200 parents at once: results + fees (400 requests) | 4.8 s | 8.7 s | 9.8 s |
| 50 report-card PDFs at once (AC5: each < 5 s, all < 2 min) | 1.8 s | 2.7 s | 2.8 s ✅ |
| Portal pages *during* the PDF burst | 1.5 s | 2.5 s | (not blocked) |

- About **40 requests a second** per API process. A request costs ~25 ms of
  CPU (mostly framework work; each page needs only 3–7 small queries).
- PDFs render in a background thread, so one parent downloading a report card
  doesn't freeze everyone else's pages.
- **Render free has a fraction of one CPU**, so expect roughly a tenth of this:
  fine for everyday use, **slow on results day** when hundreds of parents arrive
  in the same hour. Before publishing a term's results, move the API to
  Render Starter (about $7/month, a whole share of a CPU and no sleep).

## Error reports (Sentry, R27)

Set `DL360_SENTRY_DSN` (Render) and `NEXT_PUBLIC_SENTRY_DSN` (Vercel). To prove
both work (AC12), sign in as an admin on the site, open the browser console, and run:

```js
dl360SentryTest(); // frontend test error
fetch("/api/health/sentry-test", { method: "POST", headers: { "X-CSRF-Token":
  document.cookie.match(/dl360_csrf=([^;]+)/)[1] } }); // backend test error (500)
```

Both should appear in Sentry within a minute. No personal data is sent.

## When something goes wrong

| Symptom | First step |
|---|---|
| "We can't reach the school's server" | Render dashboard → `dl360-api` → Logs. Asleep? Check the UptimeRobot monitor. |
| A parent paid online but the invoice still shows a balance | Run the reconcile script. Then check Paystack → Transactions for the reference (`DL360-…`). |
| A transfer proof looks fake or duplicated | Reject it with a reason; the parent sees it. Duplicates are flagged automatically. |
| Wrong score on a published result | The principal uses **Unpublish** with a reason (audited), fixes, re-publishes. |
| Someone lost their 2FA phone | They use a recovery code. If none are left there is no in-app reset yet: ask Claude to clear their 2FA from Anthony's PC so they set it up again at next sign-in. |
| Data looks wrong after a deploy | Restore drill on the latest backup first, then decide; don't edit the database by hand. |

## Before a paying school

- Render: **Starter** for the API (no sleep, more CPU); paid Key Value.
- Database: a plan with point-in-time recovery; run the restore drill on it.
- Vercel: **Pro** (Hobby is for non-commercial use only).
- Domain: buy it, add `*.<domain>` to Vercel, set `DL360_BASE_DOMAIN` on both
  sides, remove `DL360_DEFAULT_SCHOOL_SLUG`.
- Email: `DL360_RESEND_API_KEY` and a verified sending domain (parent sign-in codes).
- Sentry: DSNs set and both test errors received.
- Paystack: live keys (production only), the school's subaccount code in Fee
  setup, and one real ₦100 payment end to end.
- `pnpm check` and `pnpm e2e` green on the commit being deployed.
