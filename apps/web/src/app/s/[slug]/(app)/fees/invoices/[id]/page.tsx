"use client";

import Link from "next/link";
import { use } from "react";
import { useFeesGetInvoice } from "@dl360/api-client";
import { ArrowLeft } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { InvoiceView } from "@/components/fees/invoice-view";
import { useMe } from "@/components/shell/me-context";
import { Skeleton } from "@/components/ui/skeleton";

export default function InvoicePage({ params }: PageProps<"/s/[slug]/fees/invoices/[id]">) {
  const { id } = use(params);
  const me = useMe();
  const q = useFeesGetInvoice(id, { query: { retry: false } });
  const manages = me.roles.includes("bursar") || me.roles.includes("school_admin");
  return (
    <div className="grid max-w-3xl gap-4">
      <Link href={manages ? "/fees/invoices" : "/fees"} className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> {manages ? "Invoices" : "School fees"}
      </Link>
      {q.isError ? (
        <p className="text-muted-foreground">{errorText(q.error)}</p>
      ) : q.data ? (
        <InvoiceView invoice={q.data.data} canManage={manages} canPay={me.kind === "parent"} />
      ) : (
        <Skeleton className="h-96" />
      )}
    </div>
  );
}
