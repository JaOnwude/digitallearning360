"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getReportsArmReportsPdfUrl,
  getResultsBroadsheetQueryKey,
  useResultsApprove,
  useResultsPublish,
  useResultsReturnForCorrections,
  useResultsSubmit,
  useResultsUnpublish,
  type BroadsheetOut,
} from "@dl360/api-client";
import { AlertTriangle, CheckCircle2, Download, Send, Undo2, Upload } from "lucide-react";
import { withToast } from "@/components/kit/notify";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

const ACTION_COPY: Record<string, { label: string; confirm: string; done: string }> = {
  submit: { label: "Submit for approval", confirm: "Submit these results to the principal? Teachers can no longer change scores unless the results are returned.", done: "Submitted for approval" },
  approve: { label: "Approve", confirm: "Approve these results? Comments close after approval.", done: "Approved" },
  publish: { label: "Publish to parents", confirm: "Publish? Parents and students will see these results and report cards straight away.", done: "Published. Parents can now see the results." },
  return: { label: "Return for corrections", confirm: "Return these results to draft so teachers can make corrections?", done: "Returned for corrections" },
};

export function Broadsheet({ armId, data }: { armId: string; data: BroadsheetOut }) {
  const queryClient = useQueryClient();
  const submit = useResultsSubmit();
  const approve = useResultsApprove();
  const publish = useResultsPublish();
  const back = useResultsReturnForCorrections();
  const unpublish = useResultsUnpublish();
  const [reason, setReason] = useState("");
  const [unpublishing, setUnpublishing] = useState(false);
  const mutations = { submit, approve, publish, return: back } as const;
  const busy = submit.isPending || approve.isPending || publish.isPending || back.isPending;

  const refresh = () => queryClient.invalidateQueries({ queryKey: getResultsBroadsheetQueryKey({ arm_id: armId }) });

  async function run(action: keyof typeof mutations) {
    if (!confirm(ACTION_COPY[action].confirm)) return;
    if (await withToast(mutations[action].mutateAsync({ armId }), ACTION_COPY[action].done)) await refresh();
  }

  async function doUnpublish() {
    if (await withToast(unpublish.mutateAsync({ armId, data: { reason } }), "Unpublished. Results are back in progress.")) {
      setUnpublishing(false);
      setReason("");
      await refresh();
    }
  }

  return (
    <div className="grid gap-4">
      {data.missing.length > 0 && (
        <div className="bg-warning/15 grid gap-1 rounded-lg p-3 text-sm">
          <p className="flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" /> Not ready to submit yet
          </p>
          <ul className="text-muted-foreground list-disc pl-6">
            {data.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {(["submit", "approve", "publish", "return"] as const)
          .filter((a) => data.allowed_actions.includes(a))
          .map((a) => (
            <Button
              key={a}
              variant={a === "return" ? "outline" : "brand"}
              onClick={() => run(a)}
              disabled={busy || (a === "submit" && data.missing.length > 0)}
            >
              {a === "submit" ? <Send /> : a === "return" ? <Undo2 /> : a === "publish" ? <Upload /> : <CheckCircle2 />}
              {ACTION_COPY[a].label}
            </Button>
          ))}
        {data.status === "published" && (
          <a href={getReportsArmReportsPdfUrl(armId)} target="_blank" rel="noopener" className={buttonVariants({ variant: "outline" })}>
            <Download /> All report cards (PDF)
          </a>
        )}
        {data.allowed_actions.includes("unpublish") && (
          <Button variant="ghost" className="text-destructive" onClick={() => setUnpublishing(true)}>
            Unpublish…
          </Button>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-xs">
          <thead className="bg-muted/50">
            <tr>
              <th className="sticky left-0 z-10 bg-inherit p-2 text-left font-medium">Student</th>
              {data.subjects.map((s) => (
                <th key={s.subject_id} className="min-w-14 p-2 text-center font-medium" title={`${s.name}${s.teacher ? ` · ${s.teacher}` : ""}`}>
                  <span className="block max-w-20 truncate">{s.name}</span>
                  <span className={s.complete ? "text-success" : "text-muted-foreground"}>{s.complete ? "✓ done" : "pending"}</span>
                </th>
              ))}
              <th className="p-2 text-center font-medium">Total</th>
              <th className="p-2 text-center font-medium">Avg</th>
              <th className="p-2 text-center font-medium" title={data.show_positions_on_cards ? "Printed on report cards" : "For staff only: not printed on report cards"}>
                Pos.
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {data.rows.map((r) => (
              <tr key={r.enrollment_id}>
                <td className="bg-background sticky left-0 z-10 p-2">
                  <span className="block text-sm font-medium whitespace-nowrap">{r.full_name}</span>
                </td>
                {data.subjects.map((s) => {
                  const cell = r.cells[s.subject_id];
                  return (
                    <td key={s.subject_id} className="p-2 text-center tabular-nums">
                      {cell ? (
                        <>
                          {Number(cell.total)}
                          <span className="text-muted-foreground ml-1">{cell.grade}</span>
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  );
                })}
                <td className="p-2 text-center font-semibold tabular-nums">{Number(r.total)}</td>
                <td className="p-2 text-center font-semibold tabular-nums">{r.average}</td>
                <td className="p-2 text-center tabular-nums">{r.position ?? "—"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-muted/30 text-sm">
            <tr>
              <td className="p-2 font-medium" colSpan={data.subjects.length + 2}>
                {data.number_in_class} in class
              </td>
              <td className="p-2 text-center font-semibold" colSpan={2}>
                Class average {data.class_average}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <Dialog open={unpublishing} onOpenChange={setUnpublishing}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unpublish {data.arm_label} results?</DialogTitle>
            <DialogDescription>
              Parents and students stop seeing these results until they&apos;re published again. Your
              reason is kept in the audit log.
            </DialogDescription>
          </DialogHeader>
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Wrong exam score entered for English" rows={3} />
          <Button variant="destructive" disabled={reason.trim().length < 10 || unpublish.isPending} onClick={doUnpublish}>
            Unpublish
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
