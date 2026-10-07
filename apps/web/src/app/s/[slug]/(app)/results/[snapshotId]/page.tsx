"use client";

import Link from "next/link";
import { use } from "react";
import { getReportsReportPdfUrl, useReportsPortalSnapshot } from "@dl360/api-client";
import { ArrowLeft, Download } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type Snap = {
  student: { name: string; class_label: string; admission_no: string };
  term: { label: string; next_term_begins: string | null };
  components: { name: string; short_name: string; max_score: number }[];
  subjects: { name: string; scores: (string | null)[]; total: string | null; grade: string | null; descriptor: string | null; cumulative_average: string | null }[];
  summary: { total: string; subjects_taken: number; average: string; class_average: string; number_in_class: number; position: number | null };
  trait_groups: { name: string; traits: { name: string; value: number | null }[] }[];
  comments: { label: string; text: string }[];
  promotion: boolean | null;
  report: { show_positions: boolean };
};

/** A published report card, readable on a phone, with the official PDF one tap away. */
export default function ResultPage({ params }: PageProps<"/s/[slug]/results/[snapshotId]">) {
  const { snapshotId } = use(params);
  const q = useReportsPortalSnapshot(snapshotId, { query: { retry: false } });
  if (q.isError) return <p className="text-muted-foreground">{errorText(q.error)}</p>;
  if (!q.data) return <Skeleton className="h-96" />;
  const d = q.data.data.data as unknown as Snap;

  return (
    <div className="grid max-w-3xl gap-5">
      <Link href="/dashboard" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> Back
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{d.student.name}</h1>
          <p className="text-muted-foreground text-sm">
            {d.student.class_label} · {d.term.label}
          </p>
        </div>
        <a href={getReportsReportPdfUrl(snapshotId)} target="_blank" rel="noopener" className={buttonVariants({ variant: "brand", size: "touch" })}>
          <Download /> Report card (PDF)
        </a>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Average" value={d.summary.average} />
        <Stat label="Class average" value={d.summary.class_average} />
        <Stat label="Total score" value={d.summary.total} />
        {d.report.show_positions && d.summary.position ? (
          <Stat label="Position" value={`${d.summary.position} of ${d.summary.number_in_class}`} />
        ) : (
          <Stat label="Subjects" value={String(d.summary.subjects_taken)} />
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Subjects</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {d.subjects.map((s) => (
              <li key={s.name} className="flex items-center gap-3 py-2.5">
                <span className="flex-1">
                  <span className="block font-medium">{s.name}</span>
                  <span className="text-muted-foreground text-xs">
                    {d.components.map((c, i) => `${c.short_name} ${s.scores[i] ?? "–"}`).join(" · ")}
                  </span>
                </span>
                <span className="text-right">
                  <span className="block font-semibold tabular-nums">{s.total ?? "—"}</span>
                  <span className="text-muted-foreground text-xs">{s.descriptor ?? ""}</span>
                </span>
                <span className="bg-brand text-brand-foreground grid size-9 place-items-center rounded-md font-bold">{s.grade ?? "–"}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {d.comments.some((c) => c.text) && (
        <Card>
          <CardHeader>
            <CardTitle>Comments</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {d.comments.filter((c) => c.text).map((c) => (
              <div key={c.label}>
                <p className="text-muted-foreground text-xs font-medium uppercase">{c.label}</p>
                <p>{c.text}</p>
              </div>
            ))}
            {d.promotion !== null && <p className="font-medium">{d.promotion ? "Promoted to the next class" : "Not promoted"}</p>}
          </CardContent>
        </Card>
      )}

      {d.trait_groups.map((g) => (
        <Card key={g.name}>
          <CardHeader>
            <CardTitle>{g.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-1 text-sm sm:grid-cols-2">
              {g.traits.map((t) => (
                <li key={t.name} className="flex justify-between gap-3 border-b py-1">
                  <span>{t.name}</span>
                  <span className="font-medium tabular-nums">{t.value ? `${t.value}/5` : "—"}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
      {d.term.next_term_begins && <p className="text-muted-foreground text-sm">Next term begins {new Date(d.term.next_term_begins).toLocaleDateString("en-NG", { day: "numeric", month: "long", year: "numeric" })}.</p>}
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
