"use client";

import Link from "next/link";
import { useResultsMyClasses } from "@dl360/api-client";
import { BookOpen, CheckCircle2, ChevronRight, Users } from "lucide-react";
import { PageHeader } from "@/components/kit/page-header";
import { StatusBadge } from "@/components/results/status-badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorText } from "@/components/auth/steps";

/** A staff member's work this term: subjects to score, and classes to review. */
export default function MyClassesPage() {
  const q = useResultsMyClasses({ query: { retry: false } });
  const data = q.data?.data;

  if (q.isError) return <p className="text-muted-foreground">{errorText(q.error)}</p>;
  if (!data) return <Skeleton className="h-72" />;

  const nothing = data.subject_classes.length === 0 && data.arm_classes.length === 0;
  return (
    <div className="grid gap-6">
      <PageHeader title="My classes" description={data.term_label} />
      {nothing && (
        <p className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
          You haven&apos;t been given any classes yet. The school admin assigns them in School setup → Teaching.
        </p>
      )}

      {data.subject_classes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="size-4" /> Subjects I teach
            </CardTitle>
            <CardDescription>Enter scores, then mark each subject complete.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y rounded-lg border">
              {data.subject_classes.map((c) => (
                <li key={`${c.arm_id}-${c.subject_id}`}>
                  <Link
                    href={`/classes/scores?arm=${c.arm_id}&subject=${c.subject_id}`}
                    className="hover:bg-muted/50 flex items-center gap-3 p-3"
                  >
                    <span className="w-20 font-medium">{c.arm_label}</span>
                    <span className="flex-1">{c.subject_name}</span>
                    {c.complete ? (
                      <span className="text-success flex items-center gap-1 text-sm">
                        <CheckCircle2 className="size-4" /> Complete
                      </span>
                    ) : (
                      <span className="text-muted-foreground text-sm">To do</span>
                    )}
                    <ChevronRight className="text-muted-foreground size-4" />
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {data.arm_classes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="size-4" /> Class results
            </CardTitle>
            <CardDescription>Ratings, comments, the broadsheet, and approval.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y rounded-lg border">
              {data.arm_classes.map((c) => (
                <li key={c.arm_id}>
                  <Link href={`/classes/${c.arm_id}`} className="hover:bg-muted/50 flex flex-wrap items-center gap-3 p-3">
                    <span className="w-20 font-medium">{c.arm_label}</span>
                    <span className="text-muted-foreground flex-1 text-sm">
                      {c.student_count} student{c.student_count === 1 ? "" : "s"}{c.is_form_teacher ? " · you're the form teacher" : ""}
                    </span>
                    <StatusBadge status={c.status} />
                    <ChevronRight className="text-muted-foreground size-4" />
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
