"use client";

import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getResultsGetConfigQueryKey,
  useResultsGetConfig,
  useResultsPutBands,
  useResultsPutCommentSlots,
  useResultsPutComponents,
  useResultsPutReportConfig,
  useResultsPutTraits,
  useSetupSetupOverview,
  type BandIO,
  type CommentAuthor,
  type CommentSlotIO,
  type ComponentIO,
  type ReportConfigIO,
  type SectionResultsConfigOut,
} from "@dl360/api-client";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { NativeSelect } from "@/components/kit/native-select";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

const AUTHORS: Record<CommentAuthor, string> = {
  form_teacher: "Form teacher",
  counsellor: "Guidance counsellor",
  section_head: "Principal / head",
};

export default function ResultsSettingsPage() {
  const overview = useSetupSetupOverview();
  const sections = overview.data?.data.sections ?? [];
  const [chosen, setSectionId] = useState<string>("");
  const sectionId = chosen || sections[0]?.id || "";

  return (
    <div className="grid max-w-4xl gap-6">
      <Link href="/setup" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> School setup
      </Link>
      <PageHeader title="Results settings" description="How each section scores, grades and prints its report cards." />
      {sections.length > 1 && (
        <NativeSelect value={sectionId} onChange={(e) => setSectionId(e.target.value)} className="w-fit" aria-label="Section">
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.display_name}
            </option>
          ))}
        </NativeSelect>
      )}
      {sectionId ? <SectionSettings key={sectionId} sectionId={sectionId} /> : <Skeleton className="h-96" />}
    </div>
  );
}

function SectionSettings({ sectionId }: { sectionId: string }) {
  const queryClient = useQueryClient();
  const q = useResultsGetConfig(sectionId);
  const cfg = q.data?.data;
  const apply = (res: unknown) => res && queryClient.setQueryData(getResultsGetConfigQueryKey(sectionId), res);
  if (!cfg) return <Skeleton className="h-96" />;
  return (
    <>
      <ComponentsCard cfg={cfg} apply={apply} />
      <BandsCard cfg={cfg} apply={apply} />
      <TraitsCard cfg={cfg} apply={apply} />
      <SlotsCard cfg={cfg} apply={apply} />
      <ReportCard cfg={cfg} apply={apply} />
    </>
  );
}

type CardProps = { cfg: SectionResultsConfigOut; apply: (res: unknown) => void };

function ComponentsCard({ cfg, apply }: CardProps) {
  const put = useResultsPutComponents();
  const [rows, setRows] = useState<ComponentIO[]>(cfg.components);
  const total = rows.reduce((s, r) => s + (Number(r.max_score) || 0), 0);
  const update = (i: number, patch: Partial<ComponentIO>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Score columns</CardTitle>
        <CardDescription>The columns teachers fill in. They must add up to 100.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {rows.map((r, i) => (
          <div key={r.id ?? i} className="flex flex-wrap items-center gap-2">
            <Input value={r.name} onChange={(e) => update(i, { name: e.target.value })} aria-label="Column name" className="w-48" />
            <Input value={r.short_name} onChange={(e) => update(i, { short_name: e.target.value })} aria-label="Short name" className="w-24" maxLength={12} />
            <span className="text-muted-foreground text-sm">out of</span>
            <Input type="number" min={1} max={100} value={r.max_score} onChange={(e) => update(i, { max_score: Number(e.target.value) })} aria-label="Maximum" className="w-20" />
            <Button variant="ghost" size="icon-sm" aria-label="Remove column" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => setRows([...rows, { name: "", short_name: "", max_score: 10 }])}>
            <Plus /> Add column
          </Button>
          <span className={total === 100 ? "text-success text-sm" : "text-destructive text-sm"}>Total: {total} / 100</span>
          <Button variant="brand" className="ml-auto" disabled={total !== 100 || put.isPending} onClick={async () => apply(await withToast(put.mutateAsync({ sectionId: cfg.section_id, data: rows }), "Score columns saved"))}>
            Save columns
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function BandsCard({ cfg, apply }: CardProps) {
  const put = useResultsPutBands();
  const [rows, setRows] = useState<BandIO[]>(cfg.bands);
  const update = (i: number, patch: Partial<BandIO>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Grade key</CardTitle>
        <CardDescription>Every whole mark from 0 to 100 must belong to exactly one grade.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input value={r.letter} onChange={(e) => update(i, { letter: e.target.value })} aria-label="Grade" className="w-16" maxLength={4} />
            <Input value={r.descriptor} onChange={(e) => update(i, { descriptor: e.target.value })} aria-label="Meaning" className="w-40" />
            <Input type="number" min={0} max={100} value={r.min_score} onChange={(e) => update(i, { min_score: Number(e.target.value) })} aria-label="From" className="w-20" />
            <span className="text-muted-foreground text-sm">to</span>
            <Input type="number" min={0} max={100} value={r.max_score} onChange={(e) => update(i, { max_score: Number(e.target.value) })} aria-label="To" className="w-20" />
            <Button variant="ghost" size="icon-sm" aria-label="Remove grade" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setRows([...rows, { letter: "", descriptor: "", min_score: 0, max_score: 0 }])}>
            <Plus /> Add grade
          </Button>
          <Button variant="brand" className="ml-auto" disabled={put.isPending} onClick={async () => apply(await withToast(put.mutateAsync({ sectionId: cfg.section_id, data: rows }), "Grade key saved"))}>
            Save grades
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TraitsCard({ cfg, apply }: CardProps) {
  const put = useResultsPutTraits();
  const [groups, setGroups] = useState(cfg.trait_groups.map((g) => ({ name: g.name, text: g.traits.join("\n") })));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Rated traits</CardTitle>
        <CardDescription>Rated 1–5 by the form teacher. One trait per line.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        {groups.map((g, i) => (
          <div key={i} className="grid gap-1.5">
            <Input value={g.name} onChange={(e) => setGroups(groups.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} aria-label="Group name" />
            <Textarea rows={8} value={g.text} onChange={(e) => setGroups(groups.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} aria-label={`${g.name} traits`} />
          </div>
        ))}
        <div className="flex gap-2 sm:col-span-2">
          <Button variant="outline" size="sm" onClick={() => setGroups([...groups, { name: "New group", text: "" }])}>
            <Plus /> Add group
          </Button>
          <Button
            variant="brand"
            className="ml-auto"
            disabled={put.isPending}
            onClick={async () =>
              apply(
                await withToast(
                  put.mutateAsync({ sectionId: cfg.section_id, data: groups.filter((g) => g.name.trim()).map((g) => ({ name: g.name, traits: g.text.split("\n").map((t) => t.trim()).filter(Boolean) })) }),
                  "Traits saved",
                ),
              )
            }
          >
            Save traits
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SlotsCard({ cfg, apply }: CardProps) {
  const put = useResultsPutCommentSlots();
  const [rows, setRows] = useState<CommentSlotIO[]>(cfg.comment_slots);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Comment boxes</CardTitle>
        <CardDescription>Each box is written by one role.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input value={r.label} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} aria-label="Box title" className="min-w-64 flex-1" />
            <NativeSelect value={r.author_role} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, author_role: e.target.value as CommentAuthor } : x)))} aria-label="Written by">
              {Object.entries(AUTHORS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </NativeSelect>
            <Button variant="ghost" size="icon-sm" aria-label="Remove box" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setRows([...rows, { label: "", author_role: "form_teacher" }])}>
            <Plus /> Add box
          </Button>
          <Button variant="brand" className="ml-auto" disabled={put.isPending} onClick={async () => apply(await withToast(put.mutateAsync({ sectionId: cfg.section_id, data: rows.filter((r) => r.label.trim()) }), "Comment boxes saved"))}>
            Save boxes
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ReportCard({ cfg, apply }: CardProps) {
  const put = useResultsPutReportConfig();
  const [r, setR] = useState<ReportConfigIO>(cfg.report);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Report card</CardTitle>
        <CardDescription>Layout and wording printed on {cfg.section_name} report cards.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 sm:max-w-lg">
        <div className="grid gap-1.5">
          <Label htmlFor="tpl">Layout</Label>
          <NativeSelect id="tpl" value={r.template} onChange={(e) => setR({ ...r, template: e.target.value })}>
            <option value="standard">Standard</option>
            <option value="ebonyi_jss">Ebonyi State JSS result sheet</option>
          </NativeSelect>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="hdr">Header line (optional)</Label>
          <Input id="hdr" value={r.header_lines?.[0] ?? ""} onChange={(e) => setR({ ...r, header_lines: e.target.value ? [e.target.value] : [] })} placeholder="e.g. EBONYI STATE SCHOOL SYSTEM" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="ttl">Title</Label>
          <Input id="ttl" value={r.title ?? ""} onChange={(e) => setR({ ...r, title: e.target.value })} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="sub">Subtitle</Label>
          <Input id="sub" value={r.subtitle ?? ""} onChange={(e) => setR({ ...r, subtitle: e.target.value || null })} />
        </div>
        <label className="flex items-center justify-between gap-4 rounded-lg border p-3">
          <span className="text-sm">Print class positions on report cards</span>
          <Switch checked={!!r.show_positions} onCheckedChange={(v) => setR({ ...r, show_positions: v })} />
        </label>
        <Button variant="brand" className="w-fit" disabled={put.isPending} onClick={async () => apply(await withToast(put.mutateAsync({ sectionId: cfg.section_id, data: r }), "Report card settings saved"))}>
          Save report card settings
        </Button>
      </CardContent>
    </Card>
  );
}
