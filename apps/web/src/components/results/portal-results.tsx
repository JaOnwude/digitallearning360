"use client";

import Link from "next/link";
import { useReportsPortalResults } from "@dl360/api-client";
import { ChevronRight, FileText, Lock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { naira } from "@/lib/money";

/** Parent: each child with their published results. Student: themself. */
export function PortalResults({ isParent }: { isParent: boolean }) {
  const q = useReportsPortalResults();
  const children = q.data?.data;
  if (!children) return <Skeleton className="h-48" />;
  if (children.length === 0) {
    return (
      <p className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
        {isParent
          ? "No children are linked to your account yet. Please contact the school."
          : "Your results will appear here once the school publishes them."}
      </p>
    );
  }
  return (
    <div className="grid gap-4">
      {children.map((child) => (
        <Card key={child.student_id}>
          <CardHeader>
            <CardTitle className="flex flex-wrap items-baseline gap-x-2">
              {child.full_name}
              {child.class_label && <span className="text-muted-foreground text-sm font-normal">{child.class_label}</span>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {child.results.length === 0 ? (
              <p className="text-muted-foreground text-sm">No published results yet.</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {child.results.map((r) => (
                  <li key={r.snapshot_id}>
                    {r.withheld ? (
                      <Link href="/fees" className="hover:bg-muted/50 flex min-h-12 items-center gap-3 p-3 text-sm">
                        <Lock className="text-muted-foreground size-5 shrink-0" />
                        <span className="flex-1">
                          <span className="block font-medium">{r.term_label}</span>
                          <span className="text-muted-foreground">
                            Results withheld — outstanding balance {naira(r.withheld_balance_kobo ?? 0)}
                          </span>
                        </span>
                        <span className="text-brand-ink shrink-0 font-medium">Pay fees</span>
                      </Link>
                    ) : (
                      <Link href={`/results/${r.snapshot_id}`} className="hover:bg-muted/50 flex min-h-12 items-center gap-3 p-3">
                        <FileText className="text-brand-ink size-5" />
                        <span className="flex-1">
                          <span className="block font-medium">{r.term_label}</span>
                          <span className="text-muted-foreground text-sm">Average {r.average}</span>
                        </span>
                        <ChevronRight className="text-muted-foreground size-4" />
                      </Link>
                    )}
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
