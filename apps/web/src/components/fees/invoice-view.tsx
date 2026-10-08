"use client";

import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getFeesGetInvoiceQueryKey,
  getFeesInvoiceDocumentUrl,
  getFeesReceiptDocumentUrl,
  useFeesAddAdjustment,
  useFeesRecordOfficePayment,
  useFeesSetResultsExempt,
  useFeesStartPaystack,
  useFeesUploadProof,
  type InvoiceDetail,
} from "@dl360/api-client";
import { Copy, CreditCard, Download, Landmark, Receipt, Upload } from "lucide-react";
import { toast } from "sonner";
import { Field, FormError } from "@/components/auth/field";
import { errorText } from "@/components/auth/steps";
import { withToast } from "@/components/kit/notify";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { naira, toKobo } from "@/lib/money";

export function BalanceBadge({ balance }: { balance: number }) {
  if (balance === 0) return <Badge className="bg-success/15 text-success-ink border-transparent">Paid</Badge>;
  if (balance < 0) return <Badge className="bg-success/15 text-success-ink border-transparent">In credit {naira(-balance)}</Badge>;
  return <Badge className="bg-warning/20 text-warning-foreground border-transparent">Owing {naira(balance)}</Badge>;
}

const PROOF_LABEL = { pending: "Waiting for the bursar", confirmed: "Confirmed", rejected: "Rejected" } as const;

/** One invoice. Parents pay or upload proof; bursars record payments and adjustments. */
export function InvoiceView({ invoice, canManage, canPay }: { invoice: InvoiceDetail; canManage: boolean; canPay: boolean }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: getFeesGetInvoiceQueryKey(invoice.id) });
  const payments = invoice.entries.filter((e) => e.kind === "payment");
  const adjustments = invoice.entries.filter((e) => e.kind !== "payment");

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{invoice.student_name}</h1>
          <p className="text-muted-foreground text-sm">
            {invoice.class_label} · {invoice.term_label} · Invoice {invoice.reference}
          </p>
        </div>
        <BalanceBadge balance={invoice.balance_kobo} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Total" value={naira(invoice.total_kobo)} />
        <Stat label="Paid" value={naira(invoice.paid_kobo)} />
        <Stat label="Balance" value={naira(Math.max(invoice.balance_kobo, 0))} strong />
      </div>

      {canPay && invoice.balance_kobo > 0 && <PayCard invoice={invoice} onChanged={refresh} />}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Fees</CardTitle>
          <a href={getFeesInvoiceDocumentUrl(invoice.id)} target="_blank" rel="noopener" className={buttonVariants({ variant: "outline", size: "sm" })}>
            <Download /> Invoice PDF
          </a>
        </CardHeader>
        <CardContent>
          <ul className="divide-y text-sm">
            {invoice.lines.map((l, i) => (
              <li key={i} className="flex justify-between py-2">
                <span>{l.description}</span>
                <span className="tabular-nums">{naira(l.amount_kobo)}</span>
              </li>
            ))}
            {adjustments.map((a) => (
              <li key={a.id} className="text-muted-foreground flex justify-between py-2">
                <span>{a.kind === "refund" ? "Refund" : a.note ?? "Adjustment"}</span>
                <span className="tabular-nums">{naira(a.amount_kobo)}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {payments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Payments</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {payments.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="flex-1">
                    <span className="block font-medium tabular-nums">{naira(p.amount_kobo)}</span>
                    <span className="text-muted-foreground text-xs">
                      {new Date(p.created_at).toLocaleDateString("en-NG", { dateStyle: "medium" })} · {p.note}
                    </span>
                  </span>
                  <a href={getFeesReceiptDocumentUrl(p.id)} target="_blank" rel="noopener" className={buttonVariants({ variant: "ghost", size: "sm" })}>
                    <Receipt /> Receipt
                  </a>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {invoice.proofs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Bank transfer proofs</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y text-sm">
              {invoice.proofs.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="flex-1">
                    {naira(p.claimed_amount_kobo)} {p.bank_reference && <span className="text-muted-foreground">· {p.bank_reference}</span>}
                    {p.review_note && <span className="text-muted-foreground block text-xs">{p.review_note}</span>}
                  </span>
                  <Badge variant="secondary">{PROOF_LABEL[p.status]}</Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {canManage && <ManageCard invoice={invoice} onChanged={refresh} />}
    </div>
  );
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className={strong ? "text-lg font-semibold tabular-nums" : "text-lg tabular-nums"}>{value}</p>
    </div>
  );
}

function PayCard({ invoice, onChanged }: { invoice: InvoiceDetail; onChanged: () => void }) {
  const start = useFeesStartPaystack();
  const upload = useFeesUploadProof();
  const [showUpload, setShowUpload] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function payOnline() {
    try {
      const res = await start.mutateAsync({ invoiceId: invoice.id });
      window.location.assign(res.data.authorization_url); // Paystack's secure checkout
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function submitProof(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const file = f.get("file");
    const kobo = toKobo(String(f.get("amount")));
    if (!(file instanceof File) || file.size === 0) return setError("Choose a photo or PDF of your transfer receipt.");
    if (!kobo) return setError("Enter the amount you transferred, e.g. 45,000.");
    try {
      await upload.mutateAsync({
        invoiceId: invoice.id,
        data: { file, amount_kobo: kobo, bank_reference: String(f.get("bank_reference") || "") || null, paid_on: String(f.get("paid_on") || "") || null },
      });
      toast.success("Thank you. The bursar will confirm your payment.");
      setShowUpload(false);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const bank = invoice.bank;
  return (
    <Card className="border-brand">
      <CardHeader>
        <CardTitle>Pay {naira(invoice.balance_kobo)}</CardTitle>
        {(invoice.can_pay_online || bank.account_number) && (
          <CardDescription>
            {invoice.can_pay_online && bank.account_number
              ? "Pay online in a minute, or by bank transfer and upload the receipt."
              : invoice.can_pay_online
                ? "Pay online in a minute with a card, bank transfer or USSD."
                : "Pay by bank transfer, then upload the receipt here."}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="grid gap-4">
        {invoice.can_pay_online && (
          <Button variant="brand" size="touch" onClick={payOnline} disabled={start.isPending}>
            <CreditCard /> {start.isPending ? "Opening Paystack…" : `Pay ${naira(invoice.balance_kobo)} online`}
          </Button>
        )}
        {bank.account_number ? (
          <div className="bg-muted/50 grid gap-1 rounded-lg p-3 text-sm">
            <p className="flex items-center gap-2 font-medium">
              <Landmark className="size-4" /> Bank transfer
            </p>
            <p>
              {bank.bank_name} · {bank.account_name}
            </p>
            <p className="flex items-center gap-2">
              <span className="font-mono text-base tracking-wider">{bank.account_number}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Copy account number"
                onClick={() => navigator.clipboard?.writeText(bank.account_number ?? "").then(() => toast.success("Account number copied"))}
              >
                <Copy />
              </Button>
            </p>
            <p className="text-muted-foreground text-xs">Use {invoice.reference} as the narration/description.</p>
          </div>
        ) : (
          !invoice.can_pay_online && <p className="text-muted-foreground text-sm">The school hasn&apos;t added its payment details yet. Please contact the school.</p>
        )}
        {bank.account_number &&
          (showUpload ? (
            <form onSubmit={submitProof} className="grid gap-3 rounded-lg border p-3">
              <Field id="proof-file" name="file" label="Photo or PDF of the transfer receipt" type="file" accept="image/jpeg,image/png,application/pdf" required />
              <Field id="proof-amount" name="amount" label="Amount transferred (₦)" inputMode="decimal" defaultValue={(invoice.balance_kobo / 100).toLocaleString("en-NG")} required />
              <Field id="proof-ref" name="bank_reference" label="Transaction reference (optional)" />
              <Field id="proof-date" name="paid_on" label="Date of transfer" type="date" />
              <FormError message={error} />
              <Button type="submit" variant="brand" disabled={upload.isPending}>
                {upload.isPending ? "Uploading…" : "Send to the bursar"}
              </Button>
            </form>
          ) : (
            <Button variant="outline" size="touch" onClick={() => setShowUpload(true)}>
              <Upload /> I&apos;ve paid by bank transfer
            </Button>
          ))}
      </CardContent>
    </Card>
  );
}

function ManageCard({ invoice, onChanged }: { invoice: InvoiceDetail; onChanged: () => void }) {
  const pay = useFeesRecordOfficePayment();
  const adjust = useFeesAddAdjustment();
  const exempt = useFeesSetResultsExempt();
  const [dialog, setDialog] = useState<"payment" | "adjustment" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const f = new FormData(e.currentTarget);
    const kobo = toKobo(String(f.get("amount")));
    if (!kobo) return setError("Enter an amount, e.g. 45,000.");
    const note = String(f.get("note") || "");
    try {
      if (dialog === "payment") {
        await pay.mutateAsync({ invoiceId: invoice.id, data: { amount_kobo: kobo, source: "cash", note: note || null } });
        toast.success("Payment recorded. A receipt is ready.");
      } else {
        const sign = f.get("direction") === "charge" ? 1 : -1;
        await adjust.mutateAsync({ invoiceId: invoice.id, data: { amount_kobo: sign * kobo, note } });
        toast.success("Adjustment recorded.");
      }
      setDialog(null);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bursar</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setDialog("payment")}>Record cash payment</Button>
          <Button variant="outline" onClick={() => setDialog("adjustment")}>Waiver or extra charge</Button>
        </div>
        <label className="flex items-center justify-between gap-4 rounded-lg border p-3">
          <span className="grid gap-0.5">
            <span className="text-sm font-medium">Show results despite the balance</span>
            <span className="text-muted-foreground text-xs">For an agreed payment plan. Recorded in the audit log.</span>
          </span>
          <Switch
            checked={invoice.results_exempt}
            onCheckedChange={async (v) => {
              const reason = prompt(v ? "Why should results show despite the balance?" : "Why remove the exemption?");
              if (!reason || reason.trim().length < 3) return;
              if (await withToast(exempt.mutateAsync({ invoiceId: invoice.id, data: { exempt: v, reason } }), "Saved")) onChanged();
            }}
          />
        </label>
      </CardContent>
      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent>
          {/* Keyed so each opening starts empty: a waiver's reason must never carry into a payment. */}
          <form key={dialog ?? "closed"} onSubmit={submit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{dialog === "payment" ? "Record a cash payment" : "Waiver or extra charge"}</DialogTitle>
              <DialogDescription>
                {dialog === "payment" ? "Money received at the school office. A receipt is issued." : "Changes what is owed. The reason is shown on the invoice and kept in the audit log."}
              </DialogDescription>
            </DialogHeader>
            {dialog === "adjustment" && (
              <div className="flex gap-4 text-sm">
                <label className="flex items-center gap-2"><input type="radio" name="direction" value="waiver" defaultChecked /> Waiver (reduce)</label>
                <label className="flex items-center gap-2"><input type="radio" name="direction" value="charge" /> Extra charge</label>
              </div>
            )}
            <Field id="m-amount" name="amount" label="Amount (₦)" inputMode="decimal" required />
            <Field id="m-note" name="note" label={dialog === "payment" ? "Note (optional)" : "Reason"} required={dialog === "adjustment"} minLength={dialog === "adjustment" ? 3 : undefined} />
            <FormError message={error} />
            <Button type="submit" variant="brand" disabled={pay.isPending || adjust.isPending}>Save</Button>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
