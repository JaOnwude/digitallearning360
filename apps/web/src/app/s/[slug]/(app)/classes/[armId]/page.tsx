"use client";

import Link from "next/link";
import { use } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getResultsBroadsheetQueryKey,
  getResultsReportEntryQueryKey,
  useResultsBroadsheet,
  useResultsReportEntry,
} from "@dl360/api-client";
import { ArrowLeft } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { PageHeader } from "@/components/kit/page-header";
import { Broadsheet } from "@/components/results/broadsheet";
import { ReportNotes } from "@/components/results/report-notes";
import { StatusBadge } from "@/components/results/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function ClassResultsPage({ params }: PageProps<"/s/[slug]/classes/[armId]">) {
  const { armId } = use(params);
  const queryClient = useQueryClient();
  const board = useResultsBroadsheet({ arm_id: armId }, { query: { retry: false } });
  const notes = useResultsReportEntry({ arm_id: armId }, { query: { retry: false } });

  if (board.isError) return <p className="text-muted-foreground">{errorText(board.error)}</p>;
  const b = board.data?.data;

  return (
    <div className="grid gap-4">
      <Link href="/classes" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> My classes
      </Link>
      {!b ? (
        <Skeleton className="h-96" />
      ) : (
        <>
          <PageHeader title={`${b.arm_label} results`} description={b.term_label} actions={<StatusBadge status={b.status} />} />
          <Tabs defaultValue="broadsheet">
            <TabsList>
              <TabsTrigger value="broadsheet">Broadsheet</TabsTrigger>
              <TabsTrigger value="notes">Report notes</TabsTrigger>
            </TabsList>
            <TabsContent value="broadsheet" className="pt-4">
              <Broadsheet armId={armId} data={b} />
            </TabsContent>
            <TabsContent value="notes" className="pt-4">
              {notes.data ? (
                <ReportNotes
                  data={notes.data.data}
                  onChanged={() => {
                    void queryClient.invalidateQueries({ queryKey: getResultsBroadsheetQueryKey({ arm_id: armId }) });
                    void queryClient.invalidateQueries({ queryKey: getResultsReportEntryQueryKey({ arm_id: armId }) });
                  }}
                />
              ) : (
                <Skeleton className="h-96" />
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
