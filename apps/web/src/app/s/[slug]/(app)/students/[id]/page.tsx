"use client";

import Link from "next/link";
import { use, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getStudentsGetStudentQueryKey,
  useStudentsGetStudent,
  useStudentsUpdateStudent,
  type Gender,
} from "@dl360/api-client";
import { ArrowLeft } from "lucide-react";
import { Field } from "@/components/auth/field";
import { NativeSelect } from "@/components/kit/native-select";
import { withToast } from "@/components/kit/notify";
import { PageHeader } from "@/components/kit/page-header";
import { ArmOptions, HouseOptions } from "@/components/students/arm-options";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export default function StudentPage({ params }: PageProps<"/s/[slug]/students/[id]">) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const student = useStudentsGetStudent(id);
  const update = useStudentsUpdateStudent();
  const [editing, setEditing] = useState(false);
  const s = student.data?.data;

  if (student.isError) {
    return <p className="text-muted-foreground">Student not found.</p>;
  }
  if (!s) return <Skeleton className="h-96" />;

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const text = (k: string) => String(f.get(k) ?? "").trim() || null;
    const res = await withToast(
      update.mutateAsync({
        studentId: id,
        data: {
          first_name: text("first_name") ?? undefined,
          middle_name: text("middle_name"),
          last_name: text("last_name") ?? undefined,
          gender: text("gender") as Gender | null,
          date_of_birth: text("date_of_birth"),
          arm_id: text("arm_id"),
          house_id: text("house_id"),
        },
      }),
      "Saved",
    );
    if (res) {
      queryClient.setQueryData(getStudentsGetStudentQueryKey(id), res);
      setEditing(false);
    }
  }

  return (
    <div className="grid max-w-3xl gap-6">
      <Link href="/students" className="text-muted-foreground flex w-fit items-center gap-1 text-sm hover:underline">
        <ArrowLeft className="size-4" /> Students
      </Link>
      <PageHeader
        title={s.full_name}
        description={`${s.admission_no} · ${s.class_name ?? "Not placed in a class"}`}
        actions={!editing && <Button variant="outline" onClick={() => setEditing(true)}>Edit</Button>}
      />

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          {editing ? (
            <form onSubmit={save} className="grid gap-3 sm:grid-cols-2">
              <Field id="e-first" name="first_name" label="First name" defaultValue={s.first_name} required />
              <Field id="e-last" name="last_name" label="Surname" defaultValue={s.last_name} required />
              <Field id="e-middle" name="middle_name" label="Other names" defaultValue={s.middle_name ?? ""} />
              <Field id="e-dob" name="date_of_birth" label="Date of birth" type="date" defaultValue={s.date_of_birth ?? ""} />
              <div className="grid gap-1.5">
                <Label htmlFor="e-gender">Gender</Label>
                <NativeSelect id="e-gender" name="gender" defaultValue={s.gender ?? ""} className="h-11">
                  <option value="">—</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="e-arm">Class</Label>
                <NativeSelect id="e-arm" name="arm_id" defaultValue={s.arm_id ?? ""} className="h-11">
                  <ArmOptions />
                </NativeSelect>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="e-house">House</Label>
                <NativeSelect id="e-house" name="house_id" defaultValue={s.house_id ?? ""} className="h-11">
                  <option value="">—</option>
                  <HouseOptions />
                </NativeSelect>
              </div>
              <div className="flex gap-2 sm:col-span-2">
                <Button type="submit" variant="brand" disabled={update.isPending}>Save</Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </form>
          ) : (
            <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
              <dt className="text-muted-foreground">Gender</dt>
              <dd className="capitalize">{s.gender ?? "—"}</dd>
              <dt className="text-muted-foreground">Date of birth</dt>
              <dd>{s.date_of_birth ?? "—"}</dd>
              <dt className="text-muted-foreground">House</dt>
              <dd>{s.house ?? "—"}</dd>
              <dt className="text-muted-foreground">Sign-in</dt>
              <dd>{s.has_login ? "Has a student sign-in" : "No sign-in yet (issue a slip from the student list)"}</dd>
            </dl>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Parents and guardians</CardTitle>
        </CardHeader>
        <CardContent>
          {s.guardians.length === 0 ? (
            <p className="text-muted-foreground text-sm">None recorded.</p>
          ) : (
            <ul className="divide-y">
              {s.guardians.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-sm">
                  <span className="font-medium">{g.full_name}</span>
                  {g.relationship && <span className="text-muted-foreground">{g.relationship}</span>}
                  <span>{g.email ?? ""}</span>
                  <span>{g.phone ?? ""}</span>
                  {g.has_account && <Badge variant="secondary">Uses the portal</Badge>}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
