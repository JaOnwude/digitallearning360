"use client";

import { useState, type FormEvent } from "react";
import {
  useSetupCreateArm,
  useSetupDeleteArm,
  useSetupRenameLevel,
  useSetupUpdateSection,
  type LevelOut,
  type SectionOut,
} from "@dl360/api-client";
import { Plus, X } from "lucide-react";
import { withToast } from "@/components/kit/notify";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSetup } from "./use-setup";

/** One card per section: its printed name, student sign-in, and classes with their arms. */
export function SectionCard({ section }: { section: SectionOut }) {
  const { apply } = useSetup();
  const update = useSetupUpdateSection();
  const [name, setName] = useState(section.display_name);

  async function saveName(e: FormEvent) {
    e.preventDefault();
    apply(
      await withToast(
        update.mutateAsync({ sectionId: section.id, data: { display_name: name } }),
        "Name saved",
      ),
    );
  }

  async function toggleStudentLogin(enabled: boolean) {
    apply(
      await withToast(
        update.mutateAsync({ sectionId: section.id, data: { student_login_enabled: enabled } }),
        enabled ? "Students can now sign in" : "Student sign-in turned off",
      ),
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{section.name}</CardTitle>
        <CardDescription>Classes, arms and how this section appears on documents.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <form onSubmit={saveName} className="grid gap-1.5 sm:max-w-md">
          <Label htmlFor={`name-${section.id}`}>Name on report cards and invoices</Label>
          <div className="flex gap-2">
            <Input id={`name-${section.id}`} value={name} onChange={(e) => setName(e.target.value)} />
            <Button type="submit" variant="outline" disabled={name === section.display_name || update.isPending}>
              Save
            </Button>
          </div>
        </form>

        <label className="flex items-center justify-between gap-4 rounded-lg border p-3 sm:max-w-md">
          <span className="grid gap-0.5">
            <span className="text-sm font-medium">Students can sign in</span>
            <span className="text-muted-foreground text-xs">
              Usually on for secondary, off for nursery and primary.
            </span>
          </span>
          <Switch checked={section.student_login_enabled} onCheckedChange={toggleStudentLogin} />
        </label>

        <div className="grid gap-3">
          <h3 className="text-sm font-medium">Classes and arms</h3>
          <ul className="divide-y rounded-lg border">
            {section.levels.map((level) => (
              <LevelRow key={level.id} level={level} />
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function LevelRow({ level }: { level: LevelOut }) {
  const { apply } = useSetup();
  const rename = useSetupRenameLevel();
  const addArm = useSetupCreateArm();
  const deleteArm = useSetupDeleteArm();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(level.name);
  const [armName, setArmName] = useState("");

  async function saveName(e: FormEvent) {
    e.preventDefault();
    const res = await withToast(rename.mutateAsync({ levelId: level.id, data: { name } }), "Class renamed");
    if (res) {
      apply(res);
      setEditing(false);
    }
  }

  async function createArm(e: FormEvent) {
    e.preventDefault();
    const res = await withToast(
      addArm.mutateAsync({ data: { class_level_id: level.id, name: armName.trim() } }),
      `Arm ${level.name} ${armName.trim()} added`,
    );
    if (res) {
      apply(res);
      setArmName("");
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 p-3">
      {editing ? (
        <form onSubmit={saveName} className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} className="h-8 w-28" autoFocus />
          <Button type="submit" size="sm">Save</Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="w-20 text-left font-medium hover:underline"
          title="Rename class"
        >
          {level.name}
        </button>
      )}
      <ul className="flex flex-wrap items-center gap-2" aria-label={`Arms in ${level.name}`}>
        {level.arms.map((arm) => (
          <li key={arm.id} className="bg-muted flex items-center gap-1 rounded-full py-0.5 pr-1 pl-3 text-sm">
            {arm.name}
            <span className="text-muted-foreground text-xs">· {arm.student_count}</span>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`Remove arm ${level.name} ${arm.name}`}
              disabled={arm.student_count > 0}
              title={arm.student_count > 0 ? "Move its students first" : "Remove arm"}
              onClick={async () => apply(await withToast(deleteArm.mutateAsync({ armId: arm.id }), "Arm removed"))}
            >
              <X />
            </Button>
          </li>
        ))}
        <li>
          <form onSubmit={createArm} className="flex items-center gap-1">
            <Input
              value={armName}
              onChange={(e) => setArmName(e.target.value)}
              placeholder="New arm"
              aria-label={`New arm for ${level.name}`}
              className="h-7 w-24 text-sm"
              maxLength={30}
            />
            <Button type="submit" size="icon-sm" variant="outline" aria-label="Add arm" disabled={!armName.trim()}>
              <Plus />
            </Button>
          </form>
        </li>
      </ul>
    </li>
  );
}
