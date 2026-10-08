# Testing DigitalLearning360 on your own PC

A walk through every feature in the order a school uses them, with what you should
see at each step. About 45 minutes end to end. Accounts and passwords are in
`.local-test-accounts.md` (on Anthony's PC only; never share them).

## 0. Start it

You need Docker Desktop running. In a terminal, in the project folder:

```bash
docker compose -f infra/docker-compose.yml up -d
pnpm dev
```

Wait for `api` to say *Application startup complete* and `web` to say *Ready*, then
open **http://progress.digitallearning360.localhost:3360**.

Keep that terminal visible: parents' sign-in codes appear there (no real email locally).
Stop with **Ctrl+C**. If the API stops picking up code changes, stop and run `pnpm dev`
again.

**Two-step sign-in codes:** admin and bursar need a 6-digit code. Either add the setup
key from `.local-test-accounts.md` to Google/Microsoft Authenticator on your phone, or
run (from the project folder, with the key in place of `<KEY>`):

```bash
cd apps/api && uv run python -c "import pyotp; print(pyotp.TOTP('<KEY>').now())"
```

Each code works **once**. If one is refused as "already used", wait for the next.

**Tip:** use a normal window for staff and a private/incognito window for the parent
or student, so you can be signed in as both at once.

## 1. Admin: set up the school

Sign in: **Staff** tab → admin email + password → 2FA code.

| Do | Expect |
|---|---|
| **School setup** | Classes JSS1–3 with arms, terms, subjects. Add an arm (e.g. JSS1 D) and a subject; rename it back. |
| **School setup → Results settings** | Score columns 10/10/10/70 adding to 100, the grade key A–F, comment boxes, traits. Try making columns add to 90: it refuses to save. |
| **Staff → Add staff** | Add a *Teacher* with any email. A temporary password is shown **once**: copy it. |
| **School setup → Teaching** | Give JSS1 B's subjects to that teacher, and make them JSS1 B's form teacher. |
| **Students** | Chinedu (JSS1 A) and Adaeze (JSS1 B). Open one: details, parent, sign-in. |
| **Students → Add student** | Add a student to JSS1 B with a parent email. |
| **Students → Import CSV** | Download the template, fill 3 rows (one with a wrong class like `JSS9`), upload. The bad row is reported with its row number; nothing is saved until you confirm. |
| **Students → tick students → Sign-in slips** | A printable PDF of student sign-in details. |

## 2. Teacher: enter scores

Sign in (Staff tab) as the new teacher with the temporary password → you must pick
your own password first.

| Do | Expect |
|---|---|
| **My classes** | JSS1 B subjects listed as *To do*. |
| Open **JSS1 B · English** | A grid: 1st CA /10, 2nd CA /10, Project /10, Exam /70. Type scores; *All changes saved* appears by itself. Total and grade update as you type. |
| Type 12 in a /10 box | Box turns red and isn't saved. |
| Fill every student → **Mark complete** | Subject shows *Complete*; the grid becomes read-only. *Edit scores again* unlocks it. |
| Open **JSS1 A · English** (if assigned) | Read-only: JSS1 A is already published. |

Complete every JSS1 B subject (or as many as you like) so the class can be submitted.

## 3. Form teacher and principal: approve and publish

| Who | Do | Expect |
|---|---|---|
| Form teacher | **My classes → JSS1 B** | Broadsheet: every subject, totals, averages. Missing subjects are listed. |
| Form teacher | **Report notes** | Rate traits and write the form teacher's comment for each student. |
| Form teacher | **Submit for approval** | Status *Submitted*; teachers can no longer change scores. |
| Admin (principal) | **My classes → JSS1 B → Approve**, then **Publish** | Status *Published*. **All report cards (PDF)** downloads the class's cards. |
| Admin | **Unpublish…** with a reason (10+ characters) | Back to *In progress*; parents stop seeing it. Publish again afterwards. The reason is kept in the audit log. |

## 4. Bursar: fees

Admin → **Staff → Add staff** with role *Bursar* (or use the bursar account in
`.local-test-accounts.md`). A new bursar must set up two-step sign-in at first sign-in
(scan the QR code), save the recovery codes, then choose a password.

| Do | Expect |
|---|---|
| **Fees → Fee setup** | Tuition ₦45,000 per term for JSS1–3. Add an item (e.g. PTA levy ₦5,000), fill the amounts, **Save this term**. Fill bank details; *Online payment is off* until a Paystack key is set. |
| **Fees → Issue invoices** | Confirms, then says how many were issued. Running it again issues none twice. Dashboard: expected / collected / outstanding by class. |
| **All invoices** | Search by name; filter *Owing* / *Paid*. Open one. |
| On an invoice: **Waiver or extra charge** | A waiver of ₦5,000 with a reason appears as a −₦5,000 line; the balance drops. |
| **Record cash payment** | The balance drops; a **Receipt** link appears (PDF with a receipt number). |
| **Invoice PDF** | The invoice with the school's bank details. |
| **Debtors (CSV)** / **Payments (CSV)** | Open in Excel: fees + waivers − paid = balance on every row. |

## 5. Parent: results, fees, transfer proof

Private window → **Parent** tab → `ngozi.okafor@example.com` → **Email me a sign-in
code** → copy the code from the `pnpm dev` terminal.

| Do | Expect |
|---|---|
| **Dashboard** | Each child. A child with unpaid fees shows **Results withheld — outstanding balance ₦X** (no average, no card). A child who has paid shows the term average. |
| Open a visible result | Subjects, CA/exam breakdown, grades, comments. **Report card (PDF)** downloads it. |
| **School fees** → an owing invoice | Balance, bank details with a copy button, the invoice PDF. |
| **I've paid by bank transfer** | Upload a photo or PDF (any image works locally), the amount, a reference. It shows *Waiting for the bursar*. |
| Upload the same file again | Accepted, but the bursar sees it flagged as a possible duplicate. |

Leave the parent window open for the next step.

## 6. Bursar: confirm the transfer

| Do | Expect |
|---|---|
| **Fees → Transfer proofs** | The parent's upload with a preview. **Confirm** prefills the claimed amount: change it if less arrived. |
| Confirm | The proof moves to *Confirmed*. In the parent window (no refresh needed, within a few seconds), the invoice updates and the receipt appears. |
| If paid in full | The parent's dashboard now shows that child's results. |
| **Reject** another proof with a reason | The parent sees *Rejected* and the reason; the balance doesn't change. |
| On an invoice: **Show results despite the balance** | Asks for a reason; the parent can see results while still owing (for payment plans). |

## 7. Student

**Student** tab → admission number (e.g. `PJS/2026/001`) + the password from a
sign-in slip (step 1).

| Do | Expect |
|---|---|
| First sign-in | Must choose a new password before anything else. |
| Dashboard | Only their own results (withheld if fees are owed). **Fees** is read-only: no pay buttons. |

## 8. Public report-card check (QR)

Open any report card PDF and scan its QR code with your phone (or open the link
under it). It shows **Genuine report card** with the name, class and term. Change one
character at the end of the link: **This report card can't be verified**.

## 9. Online payment (needs your Paystack test key)

Add `DL360_PAYSTACK_SECRET_KEY=sk_test_…` to `apps/api/.env` and restart `pnpm dev`.
The parent's invoice now shows **Pay ₦X online** → Paystack's test checkout → pay with
Paystack's test card (on their *Test payments* docs page) → you return to
*Payment received* with a receipt link.

## 10. Automated checks

```bash
pnpm check   # API tests, types, lint (about 2 minutes)
pnpm e2e     # the main flows above in a real browser, on separate ports and database
```

## If something goes wrong

| You see | Try |
|---|---|
| "We can't reach the school's server" | The API isn't running or is restarting: check the `pnpm dev` terminal; wait a few seconds, then **Try again**. |
| Port 3360 or 8360 already in use | Another `pnpm dev` is running somewhere. Close it, or restart the PC's terminal. |
| "That code was already used" | Wait for the next 6-digit code. |
| "Too many attempts" | Rate limit: wait 15 minutes, or clear local Redis (also signs everyone out): `docker compose -f infra/docker-compose.yml exec redis redis-cli FLUSHDB`. |
| No sign-in code for the parent | Look in the `pnpm dev` terminal for *Your sign-in code is …*; codes expire after 10 minutes. |

Anything else: copy the error (and the last lines of the `pnpm dev` terminal) to Claude.
