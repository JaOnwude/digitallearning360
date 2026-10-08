"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import {
  getFeesProofFileUrl,
  useFeesConfirmProof,
  useFeesListProofs,
  useFeesRejectProof,
  type ProofOut,
  type ProofStatus,
} from "@dl360/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { Field, FormError } from "@/components/auth/field";
import { errorText } from "@/components/auth/steps";
import { PageHeader } from "@/components/kit/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { naira, toKobo } from "@/lib/money";

export default function ProofsPage() {
  const [status, setStatus] = useState<ProofStatus>("pending");
  const list = useFeesListProofs({ status });
  const [reviewing, setReviewing] = useState<{ proof: ProofOut; action: "confirm" | "reject" } | null>(null);
  const proofs = list.data?.data;

  return (
    <div className="grid gap-5">
      <Link href="/fees" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> Fees
      </Link>
      <PageHeader title="Transfer proofs" description="Check each one against the school's bank statement before confirming." />
      <Tabs value={status} onValueChange={(v) => setStatus(v as ProofStatus)}>
        <TabsList>
          <TabsTrigger value="pending">To check</TabsTrigger>
          <TabsTrigger value="confirmed">Confirmed</TabsTrigger>
          <TabsTrigger value="rejected">Rejected</TabsTrigger>
        </TabsList>
      </Tabs>
      {!proofs ? (
        <Skeleton className="h-64" />
      ) : proofs.length === 0 ? (
        <p className="text-muted-foreground text-sm">{status === "pending" ? "Nothing to check. All caught up." : "None yet."}</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {proofs.map((p) => (
            <ProofCard key={p.id} proof={p} onReview={(action) => setReviewing({ proof: p, action })} />
          ))}
        </div>
      )}
      <ReviewDialog reviewing={reviewing} onClose={() => setReviewing(null)} />
    </div>
  );
}

function ProofCard({ proof: p, onReview }: { proof: ProofOut; onReview: (action: "confirm" | "reject") => void }) {
  const url = getFeesProofFileUrl(p.id);
  const isImage = p.content_type.startsWith("image/");
  return (
    <Card>
      <CardContent className="grid gap-3">
        <a href={url} target="_blank" rel="noopener" className="bg-muted relative block overflow-hidden rounded-md border">
          {isImage ? (
            // Served from our API (auth-gated); next/image can't forward the session cookie.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={`Transfer proof for ${p.student_name}`} className="max-h-72 w-full object-contain" loading="lazy" />
          ) : (
            <span className="flex h-24 items-center justify-center gap-2 text-sm">
              <ExternalLink className="size-4" /> Open PDF
            </span>
          )}
        </a>
        <div className="grid gap-1 text-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <Link href={`/fees/invoices/${p.invoice_id}`} className="font-medium hover:underline">{p.student_name}</Link>
            <span className="text-lg font-semibold tabular-nums">{naira(p.claimed_amount_kobo)}</span>
          </div>
          <p className="text-muted-foreground">
            {p.invoice_reference}
            {p.bank_reference && <> · Bank ref {p.bank_reference}</>}
            {p.paid_on && <> · Paid {new Date(p.paid_on).toLocaleDateString("en-NG")}</>}
          </p>
          <p className="text-muted-foreground text-xs">Uploaded {new Date(p.created_at).toLocaleString("en-NG")}</p>
          {p.duplicate_of && (
            <p className="text-warning-foreground bg-warning/15 flex items-center gap-2 rounded-md px-2 py-1">
              <TriangleAlert className="size-4 shrink-0" /> Possible duplicate: the same file or bank reference was uploaded before.
            </p>
          )}
          {p.status === "confirmed" && <Badge className="bg-success/15 text-success w-fit border-transparent">Confirmed {naira(p.confirmed_amount_kobo ?? 0)}</Badge>}
          {p.status === "rejected" && <p className="text-destructive">Rejected: {p.review_note}</p>}
        </div>
        {p.status === "pending" && (
          <div className="flex gap-2">
            <Button variant="brand" className="flex-1" onClick={() => onReview("confirm")}>Confirm</Button>
            <Button variant="outline" className="flex-1" onClick={() => onReview("reject")}>Reject</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ReviewDialog({ reviewing, onClose }: { reviewing: { proof: ProofOut; action: "confirm" | "reject" } | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const confirm = useFeesConfirmProof();
  const reject = useFeesRejectProof();
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!reviewing) return;
    setError(null);
    const f = new FormData(e.currentTarget);
    const { proof, action } = reviewing;
    try {
      if (action === "confirm") {
        const kobo = toKobo(String(f.get("amount")));
        if (!kobo) return setError("Enter the amount that actually arrived.");
        await confirm.mutateAsync({ proofId: proof.id, data: { amount_kobo: kobo, note: String(f.get("note") || "") || null } });
        toast.success("Payment confirmed. The parent can download the receipt.");
      } else {
        await reject.mutateAsync({ proofId: proof.id, data: { reason: String(f.get("reason")) } });
        toast.success("Proof rejected. The parent has been told why.");
      }
      void queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/fees") });
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }

  const proof = reviewing?.proof;
  return (
    <Dialog open={reviewing !== null} onOpenChange={(o) => { if (!o) { setError(null); onClose(); } }}>
      <DialogContent>
        {proof && (
          <form onSubmit={submit} className="grid gap-4">
            <DialogHeader>
              <DialogTitle>{reviewing.action === "confirm" ? "Confirm transfer" : "Reject proof"}</DialogTitle>
              <DialogDescription>
                {proof.student_name} · claimed {naira(proof.claimed_amount_kobo)}
              </DialogDescription>
            </DialogHeader>
            {reviewing.action === "confirm" ? (
              <>
                <Field id="r-amount" name="amount" label="Amount received (₦)" inputMode="decimal" required defaultValue={String(proof.claimed_amount_kobo / 100)} hint="As shown on the bank statement. If less arrived, the rest stays owing." />
                <Field id="r-note" name="note" label="Note (optional)" />
              </>
            ) : (
              <Field id="r-reason" name="reason" label="Reason (the parent sees this)" required minLength={5} maxLength={300} placeholder="e.g. No matching credit on the statement" />
            )}
            <FormError message={error} />
            <Button type="submit" variant={reviewing.action === "confirm" ? "brand" : "destructive"} disabled={confirm.isPending || reject.isPending}>
              {reviewing.action === "confirm" ? "Confirm payment" : "Reject"}
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
