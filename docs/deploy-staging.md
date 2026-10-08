# Deploying staging (Render + Vercel)

Staging = a private test copy of DigitalLearning360 on the internet, so you can
share a link. It uses free plans; going live (M4) needs paid ones (see the end).

You need: the GitHub repo `JaOnwude/digitallearning360`, Render and Vercel
accounts (both signed in with that GitHub account), and the file
`.local-staging-secrets.md` from the project folder on Anthony's PC
(it holds the two secret values; never paste them in chat or commit them).

## 0. Neon: the database (≈3 min)

Render allows one free Postgres per account, so staging uses Neon's free tier.

1. Sign up at <https://neon.tech> (GitHub sign-in is fine).
2. **Create project** → name `digitallearning360`, Postgres **16**, region
   **AWS Europe Central 1 (Frankfurt)**.
3. On the project dashboard click **Connect** and copy the connection string
   (starts with `postgresql://`, ends with `?sslmode=require...`). Keep it
   private: it contains the database password. This is the **owner** string:
   it is used only for migrations and backups.
4. Create the restricted role the API runs as (so Postgres row-level security
   keeps every school's data apart; the API refuses to start without it).
   In Neon open **SQL Editor** and run this, with the password replaced by
   `DL360_APP_DB_PASSWORD` from `.local-staging-secrets.md`:
   ```sql
   CREATE ROLE dl360_app LOGIN PASSWORD 'paste-DL360_APP_DB_PASSWORD-here'
     NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
   GRANT USAGE ON SCHEMA public TO dl360_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dl360_app;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO dl360_app;
   ```
5. Make the **app** connection string: the owner string from step 3 with the
   user and password swapped, i.e. `postgresql://dl360_app:<DL360_APP_DB_PASSWORD>@<same host>/<same db>?sslmode=require`.

## 1. Render: API and Redis (≈10 min)

1. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
2. Pick the repo **JaOnwude/digitallearning360**. Render finds `render.yaml`
   and lists: `dl360-api` (web service) and `dl360-redis` (Key Value).
   Leave the defaults. (If an earlier attempt failed, open that Blueprint and
   click **Manual sync** instead of creating a new one.)
3. It asks for the values marked secret:
   - `DL360_DATABASE_URL` → the **app** connection string (step 0.5)
   - `DL360_MIGRATION_DATABASE_URL` → the **owner** connection string (step 0.3)
   - `DL360_PROXY_KEY` → copy from `.local-staging-secrets.md`
   - `DL360_ENCRYPTION_KEY` → copy from `.local-staging-secrets.md`
   - `DL360_PAYSTACK_SECRET_KEY` → your `sk_test_…` key (test mode only on staging)
   - `DL360_RESEND_API_KEY`, `DL360_SENTRY_DSN` → leave empty for now
4. Click **Apply**. The first build takes ~5–10 minutes.
5. When `dl360-api` shows **Live**, copy its URL (looks like
   `https://dl360-api-xxxx.onrender.com`). Open `<that URL>/healthz` in a
   browser: you should see `{"status":"ok"}`.

## 2. Vercel: the web app (≈5 min)

1. Go to <https://vercel.com/new> → import **JaOnwude/digitallearning360**.
2. **Root Directory**: click *Edit* → choose `apps/web`. Framework: Next.js
   (auto-detected). Leave build settings as they are.
3. **Environment Variables** (add all four):
   | Name | Value |
   |---|---|
   | `DL360_API_INTERNAL_URL` | the Render URL from step 1.5 (no trailing slash) |
   | `DL360_PROXY_KEY` | same value as on Render |
   | `DL360_BASE_DOMAIN` | `digitallearning360.invalid` |
   | `DL360_DEFAULT_SCHOOL_SLUG` | `progress` |
4. **Deploy**. When done, Vercel shows the site URL (e.g.
   `https://digitallearning360.vercel.app`). That's the shareable staging link.

## 3. Create the school on staging (Anthony + Claude, ≈2 min)

The free Render plan has no command shell, so the school is created from
Anthony's PC against the staging database:

1. Use the **app** connection string (step 0.5).
2. Save it, on Anthony's PC only, in `apps/api/.env.staging` (git-ignored) as:
   ```
   DL360_DATABASE_URL=<Neon app connection string>
   DL360_ENV=staging
   DL360_PROXY_KEY=<same proxy key>
   DL360_ENCRYPTION_KEY=<same encryption key>
   ```
3. Ask Claude to "seed staging". It runs:
   ```
   cd apps/api
   set -a; . ./.env.staging; set +a
   uv run python -m app.scripts.seed_school seeds/progress-jss.toml --admin-email <real admin email>
   ```
   and the admin gets a temporary password to change at first sign-in.

## 4. After it's up (≈10 min)

- **Keep the API awake:** create a free monitor at <https://uptimerobot.com>
  (HTTP, every 5 minutes) for `<Render URL>/healthz`. Without it Render's
  free plan sleeps after 15 idle minutes, the first visitor waits ~1 minute,
  and the Paystack reconciliation timer stops.
- **Error reports (optional now, required before go-live):** create a Sentry
  project, then set `DL360_SENTRY_DSN` on Render and `NEXT_PUBLIC_SENTRY_DSN`
  plus `NEXT_PUBLIC_DL360_ENV=staging` on Vercel (redeploy Vercel after).
- **Backups:** see [ops.md](ops.md#backups) (weekly, from Anthony's PC).

## Going live

See [ops.md](ops.md#before-a-paying-school). In short: paid Render (no sleep),
a database plan with point-in-time recovery, Vercel Pro (Hobby is
non-commercial), the real domain, Resend for parent codes, Sentry, Paystack live
keys and the school's subaccount.
