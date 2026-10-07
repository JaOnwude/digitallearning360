"use client";

import Link from "next/link";
import { useState } from "react";
import { useStudentsIssueLogins, useStudentsListStudents, type LoginSlip } from "@dl360/api-client";
import { ChevronLeft, ChevronRight, KeyRound, Upload, UserPlus } from "lucide-react";
import { NativeSelect } from "@/components/kit/native-select";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { AddStudentDialog } from "@/components/students/add-student-dialog";
import { ArmOptions } from "@/components/students/arm-options";
import { SlipsSheet } from "@/components/students/slips-sheet";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const PAGE_SIZE = 50;

export default function StudentsPage() {
  const [q, setQ] = useState("");
  const [armId, setArmId] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [slips, setSlips] = useState<LoginSlip[] | null>(null);
  const issue = useStudentsIssueLogins();
  const list = useStudentsListStudents(
    { q: q || undefined, arm_id: armId || undefined, page, page_size: PAGE_SIZE },
    { query: { placeholderData: (prev) => prev } },
  );
  const data = list.data?.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const allOnPage = data?.items.length ? data.items.every((s) => selected.has(s.id)) : false;

  function toggle(id: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function printSlips() {
    const n = selected.size;
    if (!confirm(`Create new sign-in passwords for ${n} student${n === 1 ? "" : "s"}? Any old ones stop working.`)) return;
    const res = await withToast(issue.mutateAsync({ data: { student_ids: [...selected] } }));
    if (res) {
      setSlips(res.data);
      setSelected(new Set());
      void list.refetch();
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Students"
        description={data ? `${data.total} student${data.total === 1 ? "" : "s"}` : undefined}
        actions={
          <>
            <Link href="/students/import" className={buttonVariants({ variant: "outline" })}>
              <Upload /> Import CSV
            </Link>
            <Button variant="brand" onClick={() => setAdding(true)}>
              <UserPlus /> Add student
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          placeholder="Search name or admission no."
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          className="w-full sm:w-72"
          aria-label="Search students"
        />
        <NativeSelect
          value={armId}
          onChange={(e) => {
            setArmId(e.target.value);
            setPage(1);
          }}
          aria-label="Filter by class"
        >
          <option value="">All classes</option>
          <ArmOptions />
        </NativeSelect>
        {selected.size > 0 && (
          <Button variant="outline" onClick={printSlips} disabled={issue.isPending} className="ml-auto">
            <KeyRound /> Sign-in slips for {selected.size}
          </Button>
        )}
      </div>

      {!data ? (
        <Skeleton className="h-96" />
      ) : data.total === 0 ? (
        <div className="text-muted-foreground rounded-lg border border-dashed p-10 text-center text-sm">
          {q || armId ? "No students match." : "No students yet. Add one, or import your class lists from a spreadsheet."}
        </div>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={allOnPage}
                    onCheckedChange={(on) => data.items.forEach((s) => toggle(s.id, Boolean(on)))}
                    aria-label="Select all on this page"
                  />
                </TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Admission no.</TableHead>
                <TableHead>Class</TableHead>
                <TableHead className="hidden md:table-cell">House</TableHead>
                <TableHead className="hidden md:table-cell">Sign-in</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((s) => (
                <TableRow key={s.id} data-state={selected.has(s.id) ? "selected" : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={selected.has(s.id)}
                      onCheckedChange={(on) => toggle(s.id, Boolean(on))}
                      aria-label={`Select ${s.full_name}`}
                    />
                  </TableCell>
                  <TableCell>
                    <Link href={`/students/${s.id}`} className="font-medium hover:underline">
                      {s.full_name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{s.admission_no}</TableCell>
                  <TableCell>{s.class_name ?? <span className="text-muted-foreground">Not placed</span>}</TableCell>
                  <TableCell className="hidden md:table-cell">{s.house ?? "—"}</TableCell>
                  <TableCell className="hidden md:table-cell">
                    {s.has_login ? <Badge variant="secondary">Has sign-in</Badge> : <span className="text-muted-foreground text-xs">None</span>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button variant="outline" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft />
          </Button>
          Page {page} of {pages}
          <Button variant="outline" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            <ChevronRight />
          </Button>
        </div>
      )}

      <AddStudentDialog open={adding} onOpenChange={setAdding} />
      {slips && <SlipsSheet slips={slips} onClose={() => setSlips(null)} />}
    </div>
  );
}
