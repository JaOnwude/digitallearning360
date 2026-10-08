"use client";

import Link from "next/link";
import {
  getFeesExportDebtorsUrl,
  getFeesExportPaymentsUrl,
  useFeesFeeSummary,
  useFeesGenerateInvoices,
  useFeesMyFees,
} from "@dl360/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, FileCheck2, FilePlus2, ListChecks, Settings2 } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { BalanceBadge } from "@/components/fees/invoice-view";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { useMe } from "@/components/shell/me-context";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { naira } from "@/lib/money";

export default function FeesPage() {
  const me = useMe();
  const manages = me.roles.includes("bursar") || me.roles.includes("school_admin");
  return manages ? <BursarDashboard /> : <FamilyFees />;
}

function BursarDashboard() {
  const queryClient = useQueryClient();
  const summary = useFeesFeeSummary(undefined, { query: { retry: false } });
  const generate = useFeesGenerateInvoices();
  const s = summary.data?.data;

  async function issue() {
    if (!confirm("Issue invoices for this term to every student who doesn't have one yet?")) return;
    const res = await withToast(generate.mutateAsync({ data: {} }));
    if (res) {
      const { created, already_invoiced, no_schedule } = res.data;
      alert(`${created} invoice(s) issued. ${already_invoiced} already had one.${no_schedule ? ` ${no_schedule} student(s) are in classes without fees set.` : ""}`);
      void queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/fees") });
    }
  }

  if (summary.isError) return <p className="text-muted-foreground">{errorText(summary.error)}</p>;
  if (!s) return <Skeleton className="h-96" />;
  const pct = s.expected_kobo ? Math.round((s.collected_kobo / s.expected_kobo) * 100) : 0;

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Fees"
        description={s.term_label}
        actions={
          <>
            <Link href="/fees/setup" className={buttonVariants({ variant: "outline" })}>
              <Settings2 /> Fee setup
            </Link>
            <Button variant="brand" onClick={issue} disabled={generate.isPending}>
              <FilePlus2 /> Issue invoices
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Expected" value={naira(s.expected_kobo)} />
        <Stat label={`Collected (${pct}%)`} value={naira(s.collected_kobo)} />
        <Stat label="Outstanding" value={naira(s.outstanding_kobo)} />
        <Stat label="Fully paid" value={`${s.fully_paid} of ${s.invoices}`} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Link href="/fees/proofs" className={buttonVariants({ variant: s.pending_proofs ? "brand" : "outline" })}>
          <FileCheck2 /> Transfer proofs{s.pending_proofs ? ` (${s.pending_proofs} to check)` : ""}
        </Link>
        <Link href="/fees/invoices" className={buttonVariants({ variant: "outline" })}>
          <ListChecks /> All invoices
        </Link>
        <a href={getFeesExportDebtorsUrl()} className={buttonVariants({ variant: "ghost" })}>
          <Download /> Debtors (CSV)
        </a>
        <a href={getFeesExportPaymentsUrl()} className={buttonVariants({ variant: "ghost" })}>
          <Download /> Payments (CSV)
        </a>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>By class</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {s.classes.length === 0 ? (
            <p className="text-muted-foreground text-sm">No invoices yet this term. Set fees in Fee setup, then issue invoices.</p>
          ) : (
            <table className="w-full min-w-[32rem] text-sm">
              <thead className="text-muted-foreground text-left text-xs">
                <tr>
                  <th className="py-2 font-medium">Class</th>
                  <th className="py-2 text-right font-medium">Invoices</th>
                  <th className="py-2 text-right font-medium">Expected</th>
                  <th className="py-2 text-right font-medium">Collected</th>
                  <th className="py-2 text-right font-medium">Outstanding</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {s.classes.map((c) => (
                  <tr key={c.label}>
                    <td className="py-2 font-medium">{c.label}</td>
                    <td className="py-2 text-right tabular-nums">{c.invoices}</td>
                    <td className="py-2 text-right tabular-nums">{naira(c.expected_kobo)}</td>
                    <td className="py-2 text-right tabular-nums">{naira(c.collected_kobo)}</td>
                    <td className="py-2 text-right tabular-nums">{naira(c.outstanding_kobo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

/** Parents: each child's invoices. Students: their own (read-only). */
function FamilyFees() {
  const q = useFeesMyFees();
  const data = q.data?.data;
  if (!data) return <Skeleton className="h-64" />;
  return (
    <div className="grid gap-5">
      <PageHeader title="School fees" />
      {data.children.length === 0 && <p className="text-muted-foreground text-sm">No invoices yet.</p>}
      {data.children.map((child) => (
        <Card key={child.student_id}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-baseline gap-x-2">
              {child.student_name}
              {child.class_label && <span className="text-muted-foreground text-sm font-normal">{child.class_label}</span>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {child.invoices.length === 0 ? (
              <p className="text-muted-foreground text-sm">No invoices yet.</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {child.invoices.map((inv) => (
                  <li key={inv.id}>
                    <Link href={`/fees/invoices/${inv.id}`} className="hover:bg-muted/50 flex min-h-14 items-center gap-3 p-3">
                      <span className="flex-1">
                        <span className="block font-medium">{inv.term_label}</span>
                        <span className="text-muted-foreground text-sm">{naira(inv.total_kobo)}{inv.pending_proofs ? " · transfer being checked" : ""}</span>
                      </span>
                      <BalanceBadge balance={inv.balance_kobo} />
                      <ChevronRight className="text-muted-foreground size-4" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
