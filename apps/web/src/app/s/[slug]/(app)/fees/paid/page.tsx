"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { getFeesReceiptDocumentUrl, useFeesVerifyPaystack, type PaymentResultOut } from "@dl360/api-client";
import { CircleCheck, CircleX, LoaderCircle, Receipt } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { buttonVariants } from "@/components/ui/button";
import { naira } from "@/lib/money";

/** Paystack sends the parent back here (?reference=…). We confirm with the server. */
export default function PaidPage() {
  return (
    <Suspense>
      <Paid />
    </Suspense>
  );
}

function Paid() {
  const search = useSearchParams();
  const reference = search.get("reference") ?? search.get("trxref") ?? "";
  const verify = useFeesVerifyPaystack();
  const [result, setResult] = useState<PaymentResultOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!reference || started.current) return;
    started.current = true;
    verify.mutateAsync({ data: { reference } }).then((r) => setResult(r.data), (err) => setError(errorText(err)));
  }, [reference, verify]);

  if (!reference) return <p className="text-muted-foreground">No payment to check.</p>;
  return (
    <div className="mx-auto grid max-w-md gap-4 py-10 text-center">
      {!result && !error && (
        <>
          <LoaderCircle className="mx-auto size-10 animate-spin" />
          <p>Confirming your payment…</p>
        </>
      )}
      {error && (
        <>
          <CircleX className="text-destructive mx-auto size-12" />
          <h1 className="text-xl font-semibold">We couldn&apos;t confirm this payment yet</h1>
          <p className="text-muted-foreground text-sm">{error} If money left your account, it will show on the invoice once Paystack confirms it.</p>
        </>
      )}
      {result?.status === "paid" && (
        <>
          <CircleCheck className="text-success mx-auto size-12" />
          <h1 className="text-xl font-semibold">Payment received. Thank you!</h1>
          <p className="text-muted-foreground text-sm">
            {result.balance_kobo && result.balance_kobo > 0 ? `Remaining balance: ${naira(result.balance_kobo)}` : "This invoice is now fully paid."}
          </p>
          {result.receipt_entry_id && (
            <a href={getFeesReceiptDocumentUrl(result.receipt_entry_id)} target="_blank" rel="noopener" className={buttonVariants({ variant: "brand", size: "touch" })}>
              <Receipt /> Download receipt
            </a>
          )}
        </>
      )}
      {result && result.status !== "paid" && (
        <>
          <CircleX className="text-destructive mx-auto size-12" />
          <h1 className="text-xl font-semibold">{result.status === "failed" ? "The payment didn't go through" : "Payment still processing"}</h1>
          <p className="text-muted-foreground text-sm">No money was taken for a failed payment. You can try again from the invoice.</p>
        </>
      )}
      {result?.invoice_id && (
        <Link href={`/fees/invoices/${result.invoice_id}`} className={buttonVariants({ variant: "outline" })}>
          Back to the invoice
        </Link>
      )}
    </div>
  );
}
