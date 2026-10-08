"use client";

import Link from "next/link";
import { useState } from "react";
import { useFeesListInvoices } from "@dl360/api-client";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { BalanceBadge } from "@/components/fees/invoice-view";
import { NativeSelect } from "@/components/kit/native-select";
import { PageHeader } from "@/components/kit/page-header";
import { ArmOptions } from "@/components/students/arm-options";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { naira } from "@/lib/money";

const PAGE = 50;

export default function InvoicesPage() {
  const [q, setQ] = useState("");
  const [armId, setArmId] = useState("");
  const [owing, setOwing] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);
  const list = useFeesListInvoices(
    { q: q || undefined, arm_id: armId || undefined, owing: owing ? owing === "true" : undefined, page, page_size: PAGE },
    { query: { placeholderData: (prev) => prev } },
  );
  const data = list.data?.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1;

  return (
    <div className="grid gap-5">
      <Link href="/fees" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> Fees
      </Link>
      <PageHeader title="Invoices" description={data ? `${data.total} this term` : undefined} />
      <div className="flex flex-wrap gap-2">
        <Input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Name, admission no. or invoice no." className="w-full sm:w-72" aria-label="Search invoices" />
        <NativeSelect value={armId} onChange={(e) => { setArmId(e.target.value); setPage(1); }} aria-label="Class">
          <option value="">All classes</option>
          <ArmOptions />
        </NativeSelect>
        <NativeSelect value={owing} onChange={(e) => { setOwing(e.target.value as typeof owing); setPage(1); }} aria-label="Payment status">
          <option value="">Paid and owing</option>
          <option value="true">Owing</option>
          <option value="false">Paid</option>
        </NativeSelect>
      </div>
      {!data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Student</TableHead>
                <TableHead className="hidden sm:table-cell">Class</TableHead>
                <TableHead className="hidden md:table-cell">Invoice</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link href={`/fees/invoices/${r.id}`} className="font-medium hover:underline">{r.student_name}</Link>
                    {r.pending_proofs > 0 && <span className="text-warning-foreground ml-2 text-xs">proof to check</span>}
                  </TableCell>
                  <TableCell className="hidden sm:table-cell">{r.class_label}</TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">{r.reference}</TableCell>
                  <TableCell className="text-right tabular-nums">{naira(r.paid_kobo)} <span className="text-muted-foreground">/ {naira(r.total_kobo)}</span></TableCell>
                  <TableCell className="text-right"><BalanceBadge balance={r.balance_kobo} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /></Button>
          Page {page} of {pages}
          <Button variant="outline" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight /></Button>
        </div>
      )}
    </div>
  );
}
