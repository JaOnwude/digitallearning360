# DigitalLearning360

> Status: Draft v1 · 2026-10-06 · Owners: Anthony Ozioko, JaOnwude
> Domain: none yet. Placeholder `digitallearning360` (e.g. `{slug}.digitallearning360.localhost` in development).
> Type: project. Labels: **[Decided]** = agreed in planning, **[Assumption]** = needs confirmation.

## Summary

A multi-tenant SaaS for Nigerian schools of any shape, from creche, nursery
and primary through junior and senior secondary, alone or combined in one
school. Schools manage students, results, fees, attendance, timetables and
computer-based tests (CBT).
Parents see results, fee schedules and invoices, and pay through Paystack or by
bank transfer. It is built for many schools from day one but launched with one
pilot school (**Progress Junior Secondary School, Abakaliki, Ebonyi State**;
see [Pilot school profile](#pilot-school-profile)). Revenue is a per-student,
per-term platform fee negotiated with each school. It is a per-school setting
with a placeholder default of **₦50,000**, never hard-coded.

## Problem & Goals

**Problem.** Nigerian secondary schools still compute results in spreadsheets,
print report cards by hand, chase fees over WhatsApp, and reconcile bank alerts
against paper receipts. Existing portals are often clunky, slow on mobile, or
unreliable. The pilot school's previous vendor site is currently offline.

**Goals**
1. Teachers enter scores once. Positions, grades and report cards are produced
   automatically and released to parents only after approval.
2. Parents see each child's results, fees owed and receipts on a phone, and can
   pay without visiting the school.
3. Bursars see who has paid, with no manual reconciliation for Paystack
   payments and a single confirm/reject queue for bank transfers.
4. No school can ever see another school's data.
5. A pilot school is live by **2026-10-27** (3 weeks).

**Non-goals for the pilot** (planned for later phases)
- CBT, attendance, timetable, SMS (Phases 2–3)
- Report templates for creche, nursery and primary. The data model supports
  them in the pilot (R9, R12, R13, R16d), but their templates ship when the
  first such school signs (≈2–3 days per template).
- Public school websites (later; design tokens are built for them now)
- Self-serve school onboarding wizard, platform admin UI, custom domains
- Staff payroll, library, hostel, transport, admissions, lesson notes
- Native mobile apps (the web app is a mobile-first PWA)
- Automatic timetable generation

## Users & Use Cases

| Role | Main needs |
|---|---|
| **Parent/guardian** | See each child's published results and report card; see fee schedule and invoice; pay via Paystack or upload transfer proof; download receipts |
| **Subject teacher** | Enter CA and exam scores for their assigned class-arm-subjects; see their timetable (Phase 2) |
| **Form/class teacher** | Review the arm's scores; enter affective/psychomotor ratings and comments; submit for approval; mark the register (Phase 2). In nursery/primary the class teacher often enters every subject. |
| **Section head** (Principal, Head Teacher, Nursery Head) | Approve and publish results for their section; principal comment; promotion decisions |
| **School admin / Proprietor** | Configure sections, session, terms, classes, arms, subjects and grading; manage staff and students; view fee status across all sections |
| **Bursar** | Configure fee items; generate invoices; confirm or reject transfer proofs; see collections and outstanding balances |
| **Student** | Log in; view own published results and report card (pilot); take CBT exams (Phase 3) |
| **Guidance counsellor** | Enter the counsellor comment on report cards |
| **Platform owner** | Create schools (by script in the pilot); bill schools per student per term |

## Requirements

### Must have (pilot, 3 weeks)

**Platform and tenancy**
- R1. Every school-owned row has a `school_id`. Postgres row-level security
  (RLS) enforces isolation, in addition to checks in application code.
- R2. Each school is reached by subdomain (`{slug}.digitallearning360.<tld>`,
  final domain TBD). The base domain is configuration, never hard-coded.
  A request is scoped to exactly one school.
- R3. A seed/CLI script creates a school with its branding, bank details,
  Paystack subaccount code and first admin.

**Auth and access**
- R4. Staff log in with email and password. TOTP two-factor login is mandatory
  for Admin and Bursar.
- R5. Parents log in with phone or email plus a one-time code (no password).
- R5a. Students log in with admission number + password. Admin sets or resets
  the password (CSV import can generate initial passwords on a printable slip).
  Students must change the password at first login. Students are read-only in
  the pilot. **Student login is enabled per section.** The default is on for
  JSS and SS, and off for creche, nursery and primary, where parents use the
  portal instead.
- R6. Roles are scoped: teachers see only their assigned arm-subjects, form
  teachers only their arm, parents only their linked children, students only
  themselves.
- R7. Sessions use httpOnly, Secure, SameSite=Lax cookies backed by Redis.
  No tokens are stored in browser storage.

**Academic setup**
- R8. Sessions (e.g. `2026/2027`) contain three terms. Exactly one term is
  "current" per school.
- R9. **Sections → class levels → arms.** A school has one or more
  **sections**. Each section has an ordered list of class levels, and nothing
  about level names is hard-coded. Platform presets that a school can rename,
  add to or remove:
  - Creche: Creche (optionally by age group, e.g. Toddler)
  - Nursery: Pre-Nursery, Nursery 1, Nursery 2 (and/or KG 1–2)
  - Primary: Primary 1–6 (or Basic 1–6)
  - Junior Secondary: JSS1–JSS3
  - Senior Secondary: SS1–SS3, with streams (Science, Arts, Commercial, custom)

  Each section has its own head, display name (e.g. "Progress Junior
  Secondary School" vs "Progress Senior Secondary School") and its own report
  settings. Arms (A, B, C or names like "Gold", "Diamond") are created per
  session, with no fixed limit. All sections share the school's sessions and terms.
  The pilot uses one section (Junior Secondary). Senior Secondary is added
  when its result format is available.
- R9a. Optional **houses** per school. A student belongs to one house, and the
  house is printed on the report card.
- R10. Subjects are offered per class level and are marked compulsory or
  elective. Teachers are assigned per arm and subject.
- R11. Students and parents can be imported from CSV, with row-level error
  reporting. One parent can be linked to many students.

**Results**
- R12. Assessment components (name, order, max score) are configurable **per
  section**. They must sum to 100. Platform default: CA1 20 + CA2 20 + Exam 60.
  Pilot JSS: 1st Assessment 10 + 2nd Assessment 10 + Project 10 +
  Examination 70 **[Decided]**.
- R13. Grading scales are configurable **per section**. Each band has a
  letter, a descriptor (e.g. "Distinction") and an optional remark.
  Platform presets:
  - SS (WAEC): A1 75–100, B2 70–74, B3 65–69, C4 60–64, C5 55–59, C6 50–54,
    D7 45–49, E8 40–44, F9 0–39.
  - JSS/Primary: A 70–100, B 60–69, C 50–59, D 45–49, E 40–44, F 0–39.
  - **Pilot JSS uses the school's sheet:** A Distinction 70–100, B Excellent
    61–69, C Credit 55–60, P Pass 40–54, F Fail 0–39 **[Decided]**.
- R14. Score entry is a spreadsheet-style grid for each arm and subject. It
  validates scores against component maximums and autosaves.
- R15. Workflow: `draft → submitted (form/class teacher) → approved (section head) → published`.
  Published results are read-only. Any change needs an admin override with a
  reason, recorded in the audit log.
- R16. Computed per term: subject total, grade, overall total, student
  average, **class average** (mean of the arm's student averages), number in
  class, number of subjects, and **cumulative average per subject** across the
  terms so far in the session. Positions (subject and class, competition
  ranking 1, 2, 2, 4) are computed but **shown only if the school enables
  them**. The pilot sheet shows no positions.
- R16a. Ratings use configurable trait groups, each trait scored 1–5 with a
  key (5 Excellent … 1 Very Poor). The pilot uses "A. Social Behaviour"
  (14 traits) and "B. Motor Skills" (9 traits).
- R16b. Comments: configurable comment slots. The pilot has Guidance
  Counsellor, Form Master (character and academics) and Principal. Each slot
  is filled by the matching role. Comment banks (reusable phrases) are a
  Should-have.
- R16c. A promotion decision (Promoted / Not promoted) is recorded on the
  third-term report card by the section head, and feeds R31 bulk promotion.
  Promotion can cross sections (Nursery 2 → Primary 1, Primary 6 → JSS1,
  JSS3 → SS1).
- R16d. A section's assessment mode is one of: **scored** (components and
  grades, the default for primary and secondary), **developmental** (a skill
  checklist with descriptors such as Emerging / Developing / Achieved, plus
  teacher narrative, typical for creche and nursery), or **mixed**. The pilot
  only implements the scored mode end to end. The data model and API accept
  all three.
- R17. The report card PDF is **template-driven per section**, so a school's
  existing paper format can be reproduced. The pilot template must match
  `docs/pilot-school/result-template.pdf`, including:
  - a state header line ("Ebonyi State School System"), school name, sheet
    title, motto and crest
  - name, house, class, number in class, term, year, next term begins,
    number of subjects, total score, class average
  - subject rows: each assessment component, total, grade, cumulative average
  - key to grades and key to ratings
  - trait ratings, the three comments, date/stamp area, and promoted/not promoted
  - plus our additions: a student photo (optional) and a QR verification code
- R18. Schools can choose to withhold published results from parents and
  students when **any** balance is outstanding (balance > ₦0) for that term
  **[Decided]**. There is no threshold in the pilot. Admin can grant a
  per-student exemption, which is recorded in the audit log.

**Fees and payments**
- R19. Fee items (tuition, PTA, uniform, …) are set per class level and term,
  each mandatory or optional. Per-student discounts can be fixed or percentage.
- R20. One invoice is generated per student per term, with a unique reference
  (`{SCHOOL}-{SESSION}-{TERM}-{SEQ}`). Invoice and receipt PDFs are available.
- R21. All money is stored as integer kobo. Each invoice has a ledger of
  payments and adjustments, and its balance is derived from that ledger,
  never stored as a separate editable number.
- R22. **Paystack**:
  - Payments are initialized server-side with the school's subaccount, so
    money settles to the school's bank account.
  - A webhook (with signature checked) applies the payment.
  - Webhooks are idempotent on the Paystack reference.
  - Payments are applied under a row lock on the invoice (`SELECT … FOR UPDATE`).
  - Part payments are allowed.
- R23. **Bank transfer**:
  - The invoice shows the school's account details.
  - The parent uploads proof (image/PDF, max 5 MB) plus the transfer reference
    and amount.
  - The bursar confirms (choosing the amount actually received) or rejects
    (with a reason).
  - Duplicate proofs are flagged by file hash and reference.
- R24. The bursar dashboard shows expected, collected and outstanding amounts
  per class and arm, a list of debtors, and the proof queue. Lists can be
  exported to CSV.

**Cross-cutting**
- R25. An append-only audit log records: score changes after submission,
  publish/override, payment applied/confirmed/rejected, role changes, logins.
  Each entry stores actor, before/after values, IP and time.
- R26. Rate limits on login, one-time codes, payment start and uploads.
- R27. Errors are tracked in Sentry (frontend and backend), and logs are
  structured JSON.
- R28. Live updates over SSE: a parent sees "payment received" without
  refreshing; staff get notifications.

### Should have (pilot if time allows; otherwise Phase 2)
- R29. Paystack dedicated virtual account per student, so transfers reconcile
  automatically. This depends on Paystack approving the account for the
  feature.
- R30. Email delivery of invoices, receipts and the "results published" notice.
- R31. Bulk session-end promotion (JSS1A → JSS2A), with repeat and withdraw
  exceptions.

### Phase 2 (weeks 4–5): attendance and timetable
- Daily register per arm (form teacher). Works offline as a PWA and syncs later.
- SMS to parents on absence (Termii). Attendance feeds the report card
  automatically.
- Timetable: periods per day; arm × period → subject + teacher. Conflict
  detection for a double-booked teacher or arm. "My timetable today" view.

### Phase 3 (weeks 6–8): CBT
- Question bank per subject and level. Question types: single choice,
  multiple choice, theory (marked manually).
- Exam settings: time window, duration, shuffled questions and options,
  number of attempts, results released immediately or later.
- The server owns the timer, synced over SSE. Answers autosave at most every
  5 s. Students resume after disconnect. Exams submit automatically at time-up.
- Lab mode: IP allowlist and an invigilator console (start, pause, extend
  time). Home mode: focus and tab-switch event log, flagged for review.
- JAMB-style UI with a question navigator grid and keyboard shortcuts.
- CBT scores can feed a CA or Exam component.
- Target: 500 students starting at the same time; p95 autosave under 300 ms.

### Nice to have (later)
Public school websites (2–3 themed templates), self-serve onboarding, platform
admin and billing UI, custom domains, announcements and messaging, analytics,
admissions with entrance CBT, WhatsApp notifications.

## Proposed Approach

### Architecture

```
Browser (Next.js PWA) ──HTTPS──▶ Next.js (Vercel)
                                   │  server components + generated API client
                                   ▼
                              FastAPI (API)  ──▶ PostgreSQL 16 (RLS)
                                   │  ▲
                                   ▼  │ pub/sub
                                 Redis ◀── arq workers (PDFs, email, SMS, reconciliation)
                                   │
                   Paystack webhooks ─▶ FastAPI   ·   R2/S3 (uploads, PDFs)
```

### Stack [Decided]

| Area | Choice |
|---|---|
| Repo | Monorepo: `apps/web`, `apps/api`, `packages/api-client`, `infra/` (docker compose). pnpm for JS, **uv** for Python. |
| Frontend | Next.js (App Router) + TypeScript, Tailwind, shadcn/ui, TanStack Query, React Hook Form + Zod, Recharts |
| API contract | FastAPI generates the OpenAPI description. **Orval** generates the TS client, TanStack Query hooks and Zod schemas into `packages/api-client`. CI fails if the generated client is out of date. |
| Backend | FastAPI, Pydantic v2, **SQLAlchemy 2.0** (typed, async) and Alembic. Pydantic API schemas are kept separate from database models (no SQLModel). |
| Data | PostgreSQL 16, Redis 7 |
| Jobs | arq (Redis-based) for PDF rendering (WeasyPrint), email (Resend), SMS (Termii, Phase 2) and nightly Paystack reconciliation |
| Files | Cloudflare R2 (S3 API). Uploads go straight to R2 via signed URLs. |
| Quality | ruff, pyright, pytest + testcontainers (real Postgres); ESLint + Prettier, Vitest, Playwright; pre-commit; Conventional Commits |
| Hosting | Vercel (web). Render or Railway (API + worker). Managed Postgres with point-in-time recovery (Neon or similar). Managed Redis (Upstash or similar). Choose the region closest to Nigeria **[Assumption: eu-west until af-south options are compared]**. |
| Observability | Sentry, structured logs, uptime monitor on `/healthz` |

### Tenancy
- Requests are resolved to a school by `Host` subdomain, using a middleware
  that looks up the `schools` table (cached in Redis).
- Each request runs in a transaction that executes
  `SET LOCAL app.school_id = :id`. RLS policies on every tenant table require
  `school_id = current_setting('app.school_id')::uuid`.
- The app connects to Postgres as a non-superuser role without
  `BYPASSRLS`. Platform scripts use a separate role.
- A dedicated test suite creates two schools and checks every endpoint for
  cross-school access.

### Key data model (abridged; all tenant tables have `school_id`)

- `schools` (slug, name, branding tokens JSON, bank details, paystack_subaccount_code, settings JSON)
- `users` (email/phone, password_hash argon2id, totp_secret enc.) · `memberships` (user, school, role)
- `academic_sessions` · `terms` (session, number 1–3, starts/ends, next_term_begins, is_current)
- `sections` (name, display_name, kind: creche|nursery|primary|junior_secondary|senior_secondary|other, head, assessment_mode, student_login_enabled, sort)
- `class_levels` (section, name, sort, next_level for promotion) · `arms` (level, session, name) · `streams`
- Assessment components, grading scales, trait groups, comment slots and report templates are all scoped to **section**.
- `houses` · `students` (admission_no unique per school, bio, photo, house) · `enrollments` (student, arm, session, stream)
- `guardians` · `student_guardians`
- `subjects` · `level_subjects` · `teaching_assignments` (teacher, arm, subject, session)
- `assessment_components` · `grading_scales` · `grade_bands`
- `scores` (enrollment, subject, term, component, value) · `result_sheets` (arm, term, status, approved_by, published_at)
- `term_results` (computed: totals, average, class average, cumulative averages, positions) · `promotion_decisions`
- `trait_groups` · `traits` · `trait_ratings` · `comment_slots` (name, role allowed) · `report_comments`
- `report_templates` (per school: layout key, header lines, visible fields, show_positions)
- `fee_items` · `fee_item_levels` · `student_discounts` · `invoices` (ref, student, term, total_kobo) · `invoice_lines`
- `ledger_entries` (invoice, type: payment|adjustment|refund, amount_kobo, source: paystack|transfer|manual, external_ref unique)
- `transfer_proofs` (invoice, file_key, sha256, claimed_amount, ref, status, reviewed_by)
- `paystack_events` (event_id unique, payload, processed_at)
- `audit_log` (append-only; insert-only grant)

### Payment flow (Paystack)
1. The parent clicks Pay. The API creates a `pending` payment intent and calls
   Paystack *initialize* with the amount, the school's subaccount and the
   reference. It returns the checkout URL.
2. Paystack sends `charge.success` to the webhook. The API verifies the
   HMAC-SHA512 signature and stores the event (unique on reference). It then
   re-verifies the transaction with the Paystack API, locks the invoice row,
   inserts a ledger entry, commits, and publishes an SSE event.
3. A nightly job reconciles the last 48 hours of Paystack transactions against
   the ledger and alerts on any mismatch.

### Design system and visual references

The design-reference rules from the friend's spec apply. Each reference covers
a separate area. Never copy code, text, images or branding. Everything is
centralized in tokens.

| Surface | Reference(s) | Use it for |
|---|---|---|
| Product marketing site (later) | joincolab.io, linear.app | Editorial rhythm, type scale, whitespace |
| Portal app (staff) | Linear, Vercel dashboard, shadcn blocks | Dense tables, navigation, calm hierarchy |
| Portal app (parent/student) | Paystack dashboard, mobile banking apps; ParentSquare, Seesaw, Toddle (parent-facing views) | Mobile-first cards, clear amounts, one primary action; a single home for report cards, schedules and documents |
| CBT screen (Phase 3) | JAMB CBT layout | Familiar navigator grid, no motion, big tap targets |
| Report card / invoice PDF | Official certificate conventions | Crest, watermark, QR verification |
| School public sites (later) | **UK/Europe:** Gordonstoun, Kent College, The King's School Witney, Beau Soleil (CH). **US:** The Walker School, St George's Prep, Georgetown Day School, The Bolles School, Webb School of Knoxville (the last three are award-winning Finalsite builds) | Parent-first navigation; real student photography over stock; proof (results, outcomes) before greetings; an "Apply / Book a visit" CTA that never makes a family hunt; quick links to Term Dates, Results, Fees |

The school public-site references come from 2026 "best school website"
roundups and award lists. Review each one live before adopting a pattern.
Ideas we take from them: hero with a real photo mosaic and a proof statement;
persistent admissions CTA; a "Parents" quick-access menu (portal login, term
dates, fees, uniform); news/events as cards; a footer with address, map and
contacts. Each of the 2–3 themes must render well using only the school's logo,
two brand colors and photos.

- **Tokens** are CSS variables mapped into the Tailwind theme. They cover:
  font families and weights, type scale and line heights, color roles
  (background, foreground, primary, accent, muted, border, success, warning,
  danger), spacing scale, container widths, breakpoints, radii, borders,
  shadows, button variants, motion durations and easing. All tokens have
  light and dark values.
- **Per-school branding:** `schools.branding` holds primary and accent colors
  and the logo. At runtime these override the brand tokens only. The
  foreground color on brand surfaces is chosen automatically to meet
  WCAG AA contrast of at least 4.5:1.
- **Motion:** subtle and reusable (one motion utility module). Everything
  respects `prefers-reduced-motion`. The CBT screen has no motion.
- **Performance budget for parent pages:** at most 170 KB of JS (gzipped) per
  route, and LCP under 2.5 s on Slow 4G emulation (Moto G-class device).

### Security baseline
- OWASP ASVS Level 2 as the checklist.
- Argon2id passwords, TOTP, CSRF protection (double-submit token on mutations),
  strict CSP, security headers.
- Uploads: type checked by content, size limits, signed URLs only.
- Sensitive fields (guardian phone and address, TOTP secrets) encrypted at the
  application level.
- **Nigeria Data Protection Act 2023:**
  - Guardian consent at onboarding, and a documented data retention policy.
  - A data export/delete request flow, run manually by admin in the pilot.
  - A privacy notice per school.

## Milestones

| # | Window | Shippable slice |
|---|---|---|
| M0 | Day 1–2 | Monorepo, docker compose (Postgres, Redis), CI (lint, types, tests, client check), deploy pipeline to staging, Sentry, `CLAUDE.md` |
| M1 | Day 3–7 | Tenancy + RLS + isolation tests; auth (staff + parent OTP + TOTP); roles; academic setup screens; CSV import; seed script for pilot school; design tokens + app shell |
| M2 | Day 8–13 | Score entry grid, workflow, computation, report card PDF + QR verification page, parent portal results view, audit log |
| M3 | Day 14–19 | Fee items, invoices, Paystack + webhook + reconciliation job, transfer proof upload and bursar queue, receipts, bursar dashboard, withholding rule, SSE notifications |
| M4 | Day 20–21 | Hardening: `/security-review`, load test of results and payment endpoints, Playwright end-to-end tests on the pilot flows, backup restore drill, production deploy, pilot school data import |
| M5 | Weeks 4–5 | Attendance (offline PWA) + SMS, timetable + conflicts |
| M6 | Weeks 6–8 | CBT (lab + home) |

## Acceptance Criteria (pilot)

- AC1 (R1, R2, R6): The automated isolation suite shows that a user of school A
  gets 404 on every school-B resource across all endpoints. The RLS-only test
  (application filter bypassed) also returns zero rows.
- AC2 (R4, R5, R5a, R7): Admin and bursar cannot reach any page without TOTP.
  Parent login works with a one-time code alone. A student with an initial
  password is forced to change it, then sees only their own results. No auth token appears in
  localStorage or sessionStorage.
- AC3 (R12–R16): For a fixed fixture arm of 40 students × 12 subjects, totals,
  grades, class average, cumulative averages and positions (including ties)
  match a hand-checked spreadsheet exactly.
- AC3a (R16a–R17): A pilot report card generated from fixture data matches
  `docs/pilot-school/result-template.pdf` field for field. The principal
  signs this off side by side with their paper copy.
- AC4 (R15, R25): After publish, score edits return 409 unless they go through
  the override. Each override creates an audit entry with before/after values.
- AC5 (R17): A report card PDF renders in under 5 s per student. A batch of
  50 renders in under 2 min in the background. The QR code opens a
  verification page showing the student's name, term and a document hash match.
- AC6 (R18): With withholding on, a parent or student with a balance greater than 0 sees
  "Results withheld — outstanding balance ₦X" and cannot fetch the PDF URL.
- AC7 (R21, R22): Replaying the same Paystack webhook 5 times concurrently
  produces exactly one ledger entry. A bad signature returns 401 and is not stored.
- AC8 (R22): A Paystack test-mode payment shows the subaccount split and
  updates the parent's invoice balance over SSE within 5 s of the webhook.
- AC9 (R23): A confirmed proof creates exactly one ledger entry for the amount
  the bursar chose. Re-uploading the same file is flagged as a duplicate.
- AC10 (R11): Importing a 600-row student CSV with 5 invalid rows imports 595
  and reports the 5 with row numbers and reasons.
- AC11 (Design): The parent results and invoice pages meet the performance
  budget. axe shows no serious or critical accessibility violations. Switching
  a school's brand color updates the UI with no contrast failures.
- AC12 (Ops): A restore from backup to a fresh database succeeds and is
  documented. Sentry receives a test error from the frontend and backend in
  production.

## Risks & Open Questions

**Risks**
- **Timeline (high):** 3 weeks solo is tight even for the pilot scope. The
  "should haves" (R29–R31) are the first to slip. CBT is deliberately
  excluded from the pilot.
- **Paystack onboarding (high):** live keys, subaccounts and dedicated virtual
  accounts need business verification (CAC). **Start now.** Fallback: launch
  with transfer proofs only and turn Paystack on when approved.
- **Pilot school data (high):** Progress Schools, Abakaliki is the target
  pilot. Until we have their real report card, fee list, subjects and arm
  structure, those parts of the spec are informed guesses. Collect them in week 1.
- **Result correctness (high):** wrong positions or grades destroy trust.
  Mitigated by AC3 fixtures and the approval workflow.
- **Children's personal data (medium):** NDPA obligations. Mitigated by RLS,
  encryption, audit log and a consent flow.
- **Hosting latency and cost (medium):** compare regions before M4.

**Resolved (2026-10-06)**
- Product name: DigitalLearning360. Domain: none yet; `digitallearning360` placeholder.
- JSS grading: A 70–100, B 60–69, C 50–59, D 45–49, E 40–44, F 0–39.
- Students log in during the pilot (R5a).
- Fee withholding: any outstanding balance hides results (R18).
- Pilot school: Progress Junior Secondary School, Abakaliki, Ebonyi State.
- Design references: international school sites and parent apps added (see Design system).
- ₦45,000 is the pilot school's term fee (tuition), not the platform fee.
  The platform fee is negotiated per school; the placeholder setting is ₦50,000.
- Pilot report card template and logo received (`docs/pilot-school/`).

- Pilot grading: the school's sheet (A 70+, B 61–69, C 55–60, P 40–54, F <40).
- Pilot assessment weights: 10 / 10 / 10 / 70.
- Target market includes creche, nursery, primary and secondary, alone or combined (R9, R16d).
- Progress also runs a senior secondary school. It will be added as a second
  **section** of the same school once its result sheet is available.

**Open questions**
1. Still to come from the school: the fee schedule per class (tuition ₦45,000
   plus any other items), the number of arms per class, their houses, and the
   senior secondary result sheet.
2. When we approach the first nursery/primary school, collect its report card
   to build that template.

## Pilot school profile

Source: `docs/pilot-school/result-template.pdf` and `progress-jss-logo.jpg`.

- **Name:** Progress Junior Secondary School, Abakaliki. **Motto:** "Education
  for a Better Tomorrow". The header line on documents is "Ebonyi State School System".
- **Sections:** Junior Secondary (JSS1–JSS3) in the pilot. Senior Secondary
  will follow as a second section.
- **Term fee:** ₦45,000 (tuition). The full fee schedule is still to come.
- **Subjects (12, from the sheet):** English, Mathematics, Digital
  Technologies, History, Intermediate Science, Physical & Health Education,
  Social & Citizenship Studies, Igbo Language, Cultural & Creative Arts,
  Christian Religious Studies, Business Studies, French.
- **Assessment:** 1st Assessment (10), 2nd Assessment (10), Project (10), Examination (70) →
  Total, Grade, Cumulative Average.
- **Grade key on sheet:** A Distinction 70+, B Excellent 61–69, C Credit
  55–60, P Pass 40–54, F Fail below 40.
- **Ratings (1–5):**
  - A. Social Behaviour: Punctuality, Attendance to Class, Attentiveness,
    Initiative, Perseverance, Carrying out Assignment, Organizational Ability,
    Neatness, Politeness, Honesty, Self-discipline, Spirit of Cooperation,
    Obedience, Sense of Responsibility.
  - B. Motor Skills: Handwriting, Public Speaking, Handling Tools, Drawing,
    Painting, Musical Skills, Sports, Gymnastics, Sculptures.
- **Comments:** Guidance Counsellor; Form Master (character and academics);
  Principal. Date and stamp area. Promoted / Not promoted.
- **No positions** are shown on the sheet.
- **Brand (sampled from the logo, approximate):** gold `#F5B50A`, deep olive
  `#5C4A12`, black `#0B0B0B`, flame red `#D9261C`. Gold on black is the
  signature look. These map to the school's brand tokens: primary = gold,
  primary-foreground = black, accent = red (used sparingly). Gold text on a
  white background fails contrast, so on light surfaces brand text uses the
  olive.
