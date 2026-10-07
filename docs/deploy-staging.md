# Deploying staging (Render + Vercel)

Staging = a private test copy of DigitalLearning360 on the internet, so you can
share a link. It uses free plans; going live (M4) needs paid ones (see the end).

You need: the GitHub repo `JaOnwude/digitallearning360`, Render and Vercel
accounts (both signed in with that GitHub account), and the file
`.local-staging-secrets.md` from the project folder on Anthony's PC
(it holds the two secret values; never paste them in chat or commit them).

## 1. Render: API, database and Redis (≈10 min)

1. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
2. Pick the repo **JaOnwude/digitallearning360**. Render finds `render.yaml`
   and lists: `dl360-api` (web service), `dl360-db` (Postgres), `dl360-redis`
   (Key Value). Leave the defaults.
3. It asks for the values marked secret:
   - `DL360_PROXY_KEY` → copy from `.local-staging-secrets.md`
   - `DL360_ENCRYPTION_KEY` → copy from `.local-staging-secrets.md`
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

1. In Render → `dl360-db` → **Connect** → copy the **External Database URL**.
2. Save it, on Anthony's PC only, in `apps/api/.env.staging` (git-ignored) as:
   ```
   DL360_DATABASE_URL=<external URL>?ssl=require
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

## Going live (before M4)

- Render: upgrade `dl360-api` (no sleep after 15 min idle) and `dl360-db`
  (free Postgres expires; paid has backups). Keep Key Value on a paid plan too.
- Vercel: Hobby is non-commercial only → move to Pro for a paying school.
- Buy the domain, add `*.yourdomain` to Vercel, set `DL360_BASE_DOMAIN` on both
  sides, and remove `DL360_DEFAULT_SCHOOL_SLUG`.
- Set `DL360_RESEND_API_KEY` (parent codes) and `DL360_SENTRY_DSN`.
