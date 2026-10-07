"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getResultsGetScoresQueryKey,
  useResultsGetScores,
  useResultsSaveScores,
  useResultsSetCompletion,
  type BandIO,
  type ScoreSheetOut,
} from "@dl360/api-client";
import { CheckCircle2, Cloud, CloudAlert, LoaderCircle, Pencil } from "lucide-react";
import { errorText } from "@/components/auth/steps";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { StatusBadge } from "./status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type Cells = Record<string, Record<string, string>>; // enrollment → component → typed text
type SaveState = "saved" | "pending" | "saving" | "error";

const AUTOSAVE_MS = 1000;

function gradeFor(total: number, bands: BandIO[]): string {
  const mark = Math.floor(total + 0.5);
  return bands.find((b) => b.min_score <= mark && mark <= b.max_score)?.letter ?? "";
}

function toCells(sheet: ScoreSheetOut): Cells {
  return Object.fromEntries(
    sheet.rows.map((r) => [
      r.enrollment_id,
      Object.fromEntries(Object.entries(r.values).map(([k, v]) => [k, v == null ? "" : String(Number(v))])),
    ]),
  );
}

/** Spreadsheet-style score entry for one subject in one class (spec R14). */
export function ScoreGrid({ armId, subjectId }: { armId: string; subjectId: string }) {
  const sheetQuery = useResultsGetScores({ arm_id: armId, subject_id: subjectId }, { query: { retry: false } });
  if (sheetQuery.isError) return <p className="text-muted-foreground">{errorText(sheetQuery.error)}</p>;
  if (!sheetQuery.data) return <Skeleton className="h-96" />;
  // Keyed so a fresh server copy (e.g. after "mark complete") resets local edits cleanly.
  const sheet = sheetQuery.data.data;
  return <Grid key={`${sheet.status}-${sheet.complete}`} armId={armId} subjectId={subjectId} sheet={sheet} />;
}

function Grid({ armId, subjectId, sheet }: { armId: string; subjectId: string; sheet: ScoreSheetOut }) {
  const queryClient = useQueryClient();
  const save = useResultsSaveScores();
  const completion = useResultsSetCompletion();

  const [cells, setCells] = useState<Cells>(() => toCells(sheet));
  const [dirty, setDirty] = useState<Set<string>>(new Set()); // "enrollment|component"
  const [state, setState] = useState<SaveState>("saved");
  const [lastError, setLastError] = useState<string | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement>());

  const maxFor = (componentId: string) => sheet.components.find((c) => c.id === componentId)?.max_score ?? 100;

  function invalid(componentId: string, text: string): string | null {
    if (text.trim() === "") return null;
    const n = Number(text);
    if (!Number.isFinite(n) || n < 0) return "Not a number";
    if (n > maxFor(componentId)) return `Max ${maxFor(componentId)}`;
    if (Math.round(n * 100) !== n * 100) return "2 decimals max";
    return null;
  }

  // Debounced autosave of valid changed cells.
  useEffect(() => {
    if (dirty.size === 0) return;
    const timer = setTimeout(async () => {
      const batch = [...dirty]
        .map((k) => k.split("|") as [string, string])
        .filter(([e, c]) => invalid(c, cells[e]?.[c] ?? "") === null)
        .map(([e, c]) => {
          const text = (cells[e]?.[c] ?? "").trim();
          return { enrollment_id: e, component_id: c, value: text === "" ? null : text };
        });
      if (batch.length === 0) {
        setState("error");
        setLastError("Fix the highlighted scores to save them.");
        return;
      }
      setState("saving");
      try {
        await save.mutateAsync({ data: { arm_id: armId, subject_id: subjectId, cells: batch } });
        setDirty((prev) => {
          const next = new Set(prev);
          batch.forEach((b) => next.delete(`${b.enrollment_id}|${b.component_id}`));
          return next;
        });
        setState("saved");
        setLastError(null);
      } catch (err) {
        setState("error");
        setLastError(errorText(err));
      }
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-arm on every edit
  }, [cells, dirty]);

  // Warn before leaving with unsaved scores.
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => {
      if (dirty.size > 0) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const editable = sheet.editable;
  const components = sheet.components;

  function setCell(enrollmentId: string, componentId: string, text: string) {
    setCells((prev) => ({ ...prev, [enrollmentId]: { ...prev[enrollmentId], [componentId]: text } }));
    setDirty((prev) => new Set(prev).add(`${enrollmentId}|${componentId}`));
  }

  function move(e: KeyboardEvent<HTMLInputElement>, row: number, col: number) {
    const target =
      e.key === "Enter" || e.key === "ArrowDown" ? [row + 1, col] : e.key === "ArrowUp" ? [row - 1, col] : null;
    if (!target) return;
    e.preventDefault();
    const r = sheet.rows[target[0]];
    if (r) inputs.current.get(`${r.enrollment_id}|${components[target[1]].id}`)?.focus();
  }

  async function setComplete(complete: boolean) {
    if (complete && dirty.size > 0) return;
    const done = await withToast(
      completion.mutateAsync({ data: { arm_id: armId, subject_id: subjectId, complete } }),
      complete ? "Marked complete. The form teacher can see it's ready." : "You can edit scores again.",
    );
    if (done) await queryClient.invalidateQueries({ queryKey: getResultsGetScoresQueryKey({ arm_id: armId, subject_id: subjectId }) });
  }

  const filled = sheet.rows.filter((r) => components.every((c) => (cells[r.enrollment_id]?.[c.id] ?? "") !== "")).length;

  return (
    <div className="grid gap-4">
      <PageHeader
        title={`${sheet.subject_name} · ${sheet.arm_label}`}
        description={sheet.term_label}
        actions={<StatusBadge status={sheet.status} />}
      />

      <div className="flex flex-wrap items-center gap-3 text-sm">
        {/* Unsaved edits waiting for the debounce show as "Saving…" too. */}
        <SaveIndicator state={state === "saved" && dirty.size > 0 ? "pending" : state} error={lastError} />
        <span className="text-muted-foreground">
          {filled} of {sheet.rows.length} students fully scored
        </span>
        <div className="ml-auto">
          {sheet.complete ? (
            sheet.status === "draft" && (
              <Button variant="outline" onClick={() => setComplete(false)} disabled={completion.isPending}>
                <Pencil /> Edit scores again
              </Button>
            )
          ) : editable ? (
            <Button
              variant="brand"
              onClick={() => setComplete(true)}
              disabled={completion.isPending || dirty.size > 0 || filled < sheet.rows.length}
              title={filled < sheet.rows.length ? "Fill every score first" : undefined}
            >
              <CheckCircle2 /> Mark complete
            </Button>
          ) : null}
        </div>
      </div>

      {!editable && (
        <p className="bg-muted rounded-lg px-3 py-2 text-sm">
          {sheet.complete
            ? "This subject is marked complete, so scores are read-only."
            : sheet.status !== "draft"
              ? "Results for this class have been submitted, so scores are read-only."
              : "You can view these scores but not change them."}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[36rem] text-sm">
          <thead className="bg-muted/50 text-xs">
            <tr>
              <th className="sticky left-0 z-10 bg-inherit p-2 text-left font-medium">Student</th>
              {components.map((c) => (
                <th key={c.id} className="p-2 text-center font-medium" title={c.name}>
                  {c.short_name}
                  <span className="text-muted-foreground block font-normal">/{c.max_score}</span>
                </th>
              ))}
              <th className="p-2 text-center font-medium">Total</th>
              <th className="p-2 text-center font-medium">Grade</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {sheet.rows.map((r, rowIndex) => {
              const values = components.map((c) => cells[r.enrollment_id]?.[c.id] ?? "");
              const any = values.some((v) => v !== "");
              const hasProblem = components.some((c, i) => invalid(c.id, values[i]) !== null);
              // Invalid entries (e.g. 12 out of 10) don't count: the total shows what will be saved.
              const total = values.reduce((sum, v, i) => sum + (invalid(components[i].id, v) ? 0 : Number(v) || 0), 0);
              return (
                <tr key={r.enrollment_id}>
                  <td className="bg-background sticky left-0 z-10 p-2">
                    <span className="block font-medium">{r.full_name}</span>
                    <span className="text-muted-foreground font-mono text-xs">{r.admission_no}</span>
                  </td>
                  {components.map((c, colIndex) => {
                    const text = cells[r.enrollment_id]?.[c.id] ?? "";
                    const problem = invalid(c.id, text);
                    return (
                      <td key={c.id} className="p-1 text-center">
                        <input
                          ref={(el) => {
                            if (el) inputs.current.set(`${r.enrollment_id}|${c.id}`, el);
                          }}
                          value={text}
                          onChange={(e) => setCell(r.enrollment_id, c.id, e.target.value)}
                          onKeyDown={(e) => move(e, rowIndex, colIndex)}
                          disabled={!editable}
                          inputMode="decimal"
                          aria-label={`${c.name} for ${r.full_name}`}
                          aria-invalid={problem ? true : undefined}
                          title={problem ?? undefined}
                          className={cn(
                            "focus-visible:ring-ring/50 h-9 w-16 rounded-md border bg-transparent text-center tabular-nums outline-none focus-visible:ring-3 disabled:opacity-70",
                            problem && "border-destructive bg-destructive/10",
                          )}
                        />
                      </td>
                    );
                  })}
                  <td className="p-2 text-center font-semibold tabular-nums">{any ? total.toFixed(1).replace(/\.0$/, "") : "—"}</td>
                  <td className="p-2 text-center font-semibold">{any && !hasProblem ? gradeFor(total, sheet.bands) : ""}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground text-xs">
        Scores save automatically. Press Enter or ↓ to move down a column.
      </p>
    </div>
  );
}

function SaveIndicator({ state, error }: { state: SaveState; error: string | null }) {
  if (state === "saving" || state === "pending")
    return (
      <span className="text-muted-foreground flex items-center gap-1">
        <LoaderCircle className="size-4 animate-spin" /> Saving…
      </span>
    );
  if (state === "error")
    return (
      <span className="text-destructive flex items-center gap-1" role="alert">
        <CloudAlert className="size-4" /> {error ?? "Not saved"}
      </span>
    );
  return (
    <span className="text-success flex items-center gap-1">
      <Cloud className="size-4" /> All changes saved
    </span>
  );
}
