"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, use } from "react";
import { useReportsVerify } from "@dl360/api-client";
import { CircleCheck, CircleX } from "lucide-react";
import { SchoolLogo } from "@/components/school/school-logo";
import { Skeleton } from "@/components/ui/skeleton";

/** Public page the QR code on a printed report card opens (spec R17). */
export default function VerifyPage({ params }: PageProps<"/s/[slug]/verify/[id]">) {
  const { id } = use(params);
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-6 px-6 py-10 text-center">
      <SchoolLogo className="size-20" />
      <Suspense fallback={<Skeleton className="h-40 w-full" />}>
        <Result id={id} />
      </Suspense>
    </main>
  );
}

function Result({ id }: { id: string }) {
  const h = useSearchParams().get("h") ?? "";
  const q = useReportsVerify(id, { h }, { query: { enabled: h.length >= 8, retry: false } });
  if (h.length < 8) return <Invalid school={null} />;
  if (!q.data) return <Skeleton className="h-40 w-full" />;
  const v = q.data.data;
  if (!v.valid) return <Invalid school={v.school} />;
  return (
    <div className="grid gap-3">
      <CircleCheck className="text-success mx-auto size-12" />
      <h1 className="text-xl font-semibold">Genuine report card</h1>
      <p className="text-muted-foreground text-sm">Issued by {v.school}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border p-4 text-left text-sm">
        <dt className="text-muted-foreground">Student</dt>
        <dd className="font-medium">{v.student}</dd>
        <dt className="text-muted-foreground">Class</dt>
        <dd>{v.class_label}</dd>
        <dt className="text-muted-foreground">Term</dt>
        <dd>{v.term_label}</dd>
        <dt className="text-muted-foreground">Published</dt>
        <dd>{v.published_at ? new Date(v.published_at).toLocaleDateString("en-NG", { dateStyle: "medium" }) : ""}</dd>
      </dl>
      <p className="text-muted-foreground text-xs">Check that the name, class and term match the printed card.</p>
    </div>
  );
}

function Invalid({ school }: { school: string | null }) {
  return (
    <div className="grid gap-3">
      <CircleX className="text-destructive mx-auto size-12" />
      <h1 className="text-xl font-semibold">This report card can&apos;t be verified</h1>
      <p className="text-muted-foreground text-sm">
        It may have been changed, replaced by a corrected version, or not issued{school ? ` by ${school}` : ""}.
        Please contact the school.
      </p>
    </div>
  );
}
