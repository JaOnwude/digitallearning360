"use client";

import { useState, type FormEvent } from "react";
import {
  useSetupCreateHouse,
  useSetupCreateSubject,
  useSetupDeleteHouse,
  useSetupDeleteSubject,
  useSetupUpdateSubject,
  type SubjectOut,
} from "@dl360/api-client";
import { Plus, Trash2, X } from "lucide-react";
import { withToast } from "@/components/kit/notify";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useSetup } from "./use-setup";

/** Subjects × classes grid: tick where each subject is offered (spec R10). */
export function SubjectsCard() {
  const { overview, apply } = useSetup();
  const create = useSetupCreateSubject();
  const [name, setName] = useState("");
  if (!overview) return null;
  const levels = overview.sections.flatMap((s) => s.levels);

  async function add(e: FormEvent) {
    e.preventDefault();
    const res = await withToast(
      create.mutateAsync({ data: { name: name.trim(), level_ids: levels.map((l) => l.id) } }),
      `${name.trim()} added to every class`,
    );
    if (res) {
      apply(res);
      setName("");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subjects</CardTitle>
        <CardDescription>Tick the classes that offer each subject.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground text-xs">
              <tr>
                <th className="p-2 text-left font-medium">Subject</th>
                {levels.map((l) => (
                  <th key={l.id} className="p-2 font-medium">
                    {l.name}
                  </th>
                ))}
                <th className="p-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {overview.subjects.map((subject) => (
                <SubjectRow
                  key={subject.id}
                  subject={subject}
                  levels={levels.map((l) => ({ id: l.id, name: l.name, offered: l.subject_ids.includes(subject.id) }))}
                />
              ))}
            </tbody>
          </table>
        </div>
        <form onSubmit={add} className="flex gap-2 sm:max-w-sm">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New subject" aria-label="New subject" required />
          <Button type="submit" variant="outline" disabled={create.isPending}>
            Add subject
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SubjectRow({
  subject,
  levels,
}: {
  subject: SubjectOut;
  levels: { id: string; name: string; offered: boolean }[];
}) {
  const { apply } = useSetup();
  const update = useSetupUpdateSubject();
  const remove = useSetupDeleteSubject();

  async function toggle(levelId: string, on: boolean) {
    const level_ids = levels.filter((l) => (l.id === levelId ? on : l.offered)).map((l) => l.id);
    apply(
      await withToast(
        update.mutateAsync({ subjectId: subject.id, data: { name: subject.name, code: subject.code, level_ids } }),
      ),
    );
  }

  return (
    <tr>
      <td className="p-2 font-medium">{subject.name}</td>
      {levels.map((l) => (
        <td key={l.id} className="p-2 text-center">
          <Checkbox
            checked={l.offered}
            onCheckedChange={(on) => toggle(l.id, Boolean(on))}
            aria-label={`${subject.name} in ${l.name}`}
          />
        </td>
      ))}
      <td className="p-2 text-right">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Delete ${subject.name}`}
          onClick={async () => {
            if (confirm(`Delete ${subject.name}? This can't be undone.`)) {
              apply(await withToast(remove.mutateAsync({ subjectId: subject.id }), `${subject.name} deleted`));
            }
          }}
        >
          <Trash2 />
        </Button>
      </td>
    </tr>
  );
}

export function HousesCard() {
  const { overview, apply } = useSetup();
  const create = useSetupCreateHouse();
  const remove = useSetupDeleteHouse();
  const [name, setName] = useState("");
  if (!overview) return null;

  async function add(e: FormEvent) {
    e.preventDefault();
    const res = await withToast(create.mutateAsync({ data: { name: name.trim() } }), `${name.trim()} house added`);
    if (res) {
      apply(res);
      setName("");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Houses</CardTitle>
        <CardDescription>Optional. Printed on report cards when set.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2">
        {overview.houses.map((h) => (
          <span key={h.id} className="bg-muted flex items-center gap-1 rounded-full py-0.5 pr-1 pl-3 text-sm">
            {h.name}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove ${h.name} house`}
              onClick={async () => apply(await withToast(remove.mutateAsync({ houseId: h.id }), "House removed"))}
            >
              <X />
            </Button>
          </span>
        ))}
        <form onSubmit={add} className="flex items-center gap-1">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New house" aria-label="New house" className="h-7 w-32 text-sm" required />
          <Button type="submit" size="icon-sm" variant="outline" aria-label="Add house">
            <Plus />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
