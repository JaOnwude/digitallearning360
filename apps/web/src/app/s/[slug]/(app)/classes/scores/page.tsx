"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ArrowLeft } from "lucide-react";
import { ScoreGrid } from "@/components/results/score-grid";

function Scores() {
  const params = useSearchParams();
  const arm = params.get("arm");
  const subject = params.get("subject");
  if (!arm || !subject) return <p className="text-muted-foreground">Choose a class from My classes.</p>;
  return <ScoreGrid key={`${arm}-${subject}`} armId={arm} subjectId={subject} />;
}

export default function ScoresPage() {
  return (
    <div className="grid gap-4">
      <Link href="/classes" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> My classes
      </Link>
      <Suspense>
        <Scores />
      </Suspense>
    </div>
  );
}
