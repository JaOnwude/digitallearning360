"use client";

import { PageHeader } from "@/components/kit/page-header";
import { SectionCard } from "@/components/setup/classes-card";
import { HousesCard, SubjectsCard } from "@/components/setup/subjects-card";
import { TermsCard } from "@/components/setup/terms-card";
import { useSetup } from "@/components/setup/use-setup";
import { Skeleton } from "@/components/ui/skeleton";

export default function SetupPage() {
  const { overview } = useSetup();
  return (
    <div className="grid gap-6">
      <PageHeader title="School setup" description="Classes, arms, terms, subjects and houses." />
      {!overview ? (
        <Skeleton className="h-96" />
      ) : (
        <>
          {overview.sections.map((s) => (
            <SectionCard key={s.id} section={s} />
          ))}
          <TermsCard />
          <SubjectsCard />
          <HousesCard />
        </>
      )}
    </div>
  );
}
